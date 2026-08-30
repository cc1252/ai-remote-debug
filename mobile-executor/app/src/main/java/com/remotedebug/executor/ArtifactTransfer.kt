package com.remotedebug.executor

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink
import org.json.JSONObject
import java.io.IOException
import java.io.OutputStreamWriter
import java.io.Reader
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class ArtifactTransfer(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.MINUTES)
        .writeTimeout(10, TimeUnit.MINUTES)
        .build()
) {
    private val suCandidates = listOf("su", "/system/bin/su", "/system/xbin/su", "/sbin/su", "/vendor/bin/su")

    suspend fun downloadToFile(args: JSONObject): ShellResult = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val baseUrl = args.getString("baseUrl").trimEnd('/')
        val token = args.getString("token")
        val artifactId = args.getString("artifactId")
        val remotePath = args.getString("path")

        val request = Request.Builder()
            .url("$baseUrl/api/artifacts/$artifactId")
            .header("Authorization", "Bearer $token")
            .build()
        val response = http.newCall(request).execute()
        if (!response.isSuccessful) {
            return@withContext ShellResult(response.code, "", "download failed: ${response.code} ${response.message}", System.currentTimeMillis() - started)
        }
        val body = response.body ?: return@withContext ShellResult(1, "", "empty artifact response", System.currentTimeMillis() - started)

        val process = startRootProcess() ?: return@withContext ShellResult(127, "", "su not found in ${suCandidates.joinToString()}", System.currentTimeMillis() - started)
        val stderr = StringBuilder()
        val stdout = StringBuilder()
        val stdoutThread = drain(process.inputStream.reader(), stdout)
        val stderrThread = drain(process.errorStream.reader(), stderr)

        val writer = OutputStreamWriter(process.outputStream)
        writer.write("cat > ${quoteShell(remotePath)}\n")
        writer.flush()
        body.byteStream().use { input -> input.copyTo(process.outputStream) }
        process.outputStream.flush()
        process.outputStream.close()

        val finished = process.waitFor(args.optLong("timeoutSeconds", 300), TimeUnit.SECONDS)
        if (!finished) {
            process.destroyForcibly()
        }
        stdoutThread.join(1000)
        stderrThread.join(1000)
        if (!finished) {
            return@withContext ShellResult(-1, stdout.toString().trimEnd(), "timeout\n${stderr.toString().trimEnd()}".trim(), System.currentTimeMillis() - started)
        }
        val exit = process.exitValue()
        if (exit != 0) {
            return@withContext ShellResult(exit, stdout.toString().trimEnd(), stderr.toString().trimEnd(), System.currentTimeMillis() - started)
        }
        val stat = runRootCommand("ls -l ${quoteShell(remotePath)}", args.optLong("timeoutSeconds", 30))
        ShellResult(stat.exitCode, stat.stdout, stat.stderr, System.currentTimeMillis() - started)
    }

    suspend fun uploadFromFile(args: JSONObject): ShellResult = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val baseUrl = args.getString("baseUrl").trimEnd('/')
        val token = args.getString("token")
        val remotePath = args.getString("path")
        val artifactId = args.optString("artifactId", "")
        val uploadUrl = if (artifactId.isBlank()) "$baseUrl/api/artifacts" else "$baseUrl/api/artifacts/$artifactId"

        val process = startRootProcess() ?: return@withContext ShellResult(127, "", "su not found in ${suCandidates.joinToString()}", System.currentTimeMillis() - started)
        val stderr = StringBuilder()
        val stderrThread = drain(process.errorStream.reader(), stderr)
        val writer = OutputStreamWriter(process.outputStream)
        writer.write("cat ${quoteShell(remotePath)}\nexit\n")
        writer.flush()
        writer.close()

        val requestBody = object : RequestBody() {
            override fun contentType() = "application/octet-stream".toMediaType()

            override fun writeTo(sink: BufferedSink) {
                process.inputStream.use { input -> input.copyTo(sink.outputStream()) }
            }
        }
        val request = Request.Builder()
            .url(uploadUrl)
            .header("Authorization", "Bearer $token")
            .post(requestBody)
            .build()
        val response = http.newCall(request).execute()
        val finished = process.waitFor(args.optLong("timeoutSeconds", 300), TimeUnit.SECONDS)
        if (!finished) {
            process.destroyForcibly()
        }
        stderrThread.join(1000)
        if (!response.isSuccessful) {
            return@withContext ShellResult(response.code, "", "upload failed: ${response.code} ${response.message}", System.currentTimeMillis() - started)
        }
        if (!finished) {
            return@withContext ShellResult(-1, "", "timeout\n${stderr.toString().trimEnd()}".trim(), System.currentTimeMillis() - started)
        }
        if (process.exitValue() != 0) {
            return@withContext ShellResult(process.exitValue(), "", stderr.toString().trimEnd(), System.currentTimeMillis() - started)
        }
        val body = response.body?.string().orEmpty()
        ShellResult(0, body, stderr.toString().trimEnd(), System.currentTimeMillis() - started)
    }

    private fun runRootCommand(command: String, timeoutSeconds: Long): ShellResult {
        val started = System.currentTimeMillis()
        val process = startRootProcess() ?: return ShellResult(127, "", "su not found in ${suCandidates.joinToString()}", 0)
        val writer = OutputStreamWriter(process.outputStream)
        writer.write(command)
        writer.write("\nexit\n")
        writer.flush()
        writer.close()
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val stdoutThread = drain(process.inputStream.reader(), stdout)
        val stderrThread = drain(process.errorStream.reader(), stderr)
        val finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS)
        if (!finished) process.destroyForcibly()
        stdoutThread.join(1000)
        stderrThread.join(1000)
        return ShellResult(
            exitCode = if (finished) process.exitValue() else -1,
            stdout = stdout.toString().trimEnd(),
            stderr = stderr.toString().trimEnd(),
            durationMs = System.currentTimeMillis() - started
        )
    }

    private fun startRootProcess(): Process? {
        for (su in suCandidates) {
            try {
                return ProcessBuilder(su).start()
            } catch (_: IOException) {
            }
        }
        return null
    }

    private fun drain(reader: Reader, output: StringBuilder): Thread {
        return thread(start = true) {
            reader.use {
                val buffer = CharArray(8192)
                while (true) {
                    val count = it.read(buffer)
                    if (count < 0) break
                    output.append(buffer, 0, count)
                }
            }
        }
    }

    private fun quoteShell(value: String): String {
        return "'" + value.replace("'", "'\\''") + "'"
    }
}
