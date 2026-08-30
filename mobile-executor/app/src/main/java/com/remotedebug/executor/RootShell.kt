package com.remotedebug.executor

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.OutputStreamWriter
import java.io.Reader
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

data class ShellResult(
    val exitCode: Int,
    val stdout: String,
    val stderr: String,
    val durationMs: Long
)

class RootShell {
    private val suCandidates = listOf("su", "/system/bin/su", "/system/xbin/su", "/sbin/su", "/vendor/bin/su")

    suspend fun hasRoot(): Boolean {
        val result = execute("id -u", root = true, timeoutSeconds = 5)
        return result.exitCode == 0 && result.stdout.trim() == "0"
    }

    suspend fun execute(command: String, root: Boolean, timeoutSeconds: Long = 30): ShellResult = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val process = if (root) {
            startRootProcess() ?: return@withContext ShellResult(
                exitCode = 127,
                stdout = "",
                stderr = "su not found in ${suCandidates.joinToString()}",
                durationMs = System.currentTimeMillis() - started
            )
        } else {
            try {
                ProcessBuilder("sh").start()
            } catch (error: IOException) {
                return@withContext ShellResult(
                    exitCode = 127,
                    stdout = "",
                    stderr = error.message ?: error.toString(),
                    durationMs = System.currentTimeMillis() - started
                )
            }
        }

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
        if (!finished) {
            process.destroyForcibly()
            stdoutThread.join(1000)
            stderrThread.join(1000)
            return@withContext ShellResult(
                exitCode = -1,
                stdout = stdout.toString().trimEnd(),
                stderr = "timeout after ${timeoutSeconds}s\n${stderr.toString().trimEnd()}".trim(),
                durationMs = System.currentTimeMillis() - started
            )
        }

        stdoutThread.join(1000)
        stderrThread.join(1000)
        ShellResult(
            exitCode = process.exitValue(),
            stdout = stdout.toString().trimEnd(),
            stderr = stderr.toString().trimEnd(),
            durationMs = System.currentTimeMillis() - started
        )
    }

    suspend fun executeForBase64Stdout(command: String, timeoutSeconds: Long = 60): ShellResult = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val process = startRootProcess() ?: return@withContext ShellResult(
            exitCode = 127,
            stdout = "",
            stderr = "su not found in ${suCandidates.joinToString()}",
            durationMs = System.currentTimeMillis() - started
        )
        val writer = OutputStreamWriter(process.outputStream)
        writer.write(command)
        writer.write("\nexit\n")
        writer.flush()
        writer.close()

        val stdout = ByteArrayOutputStream()
        val stderr = StringBuilder()
        val stdoutThread = thread(start = true) { process.inputStream.use { it.copyTo(stdout) } }
        val stderrThread = drain(process.errorStream.reader(), stderr)
        val finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS)
        if (!finished) {
            process.destroyForcibly()
            stdoutThread.join(1000)
            stderrThread.join(1000)
            return@withContext ShellResult(
                exitCode = -1,
                stdout = Base64.encodeToString(stdout.toByteArray(), Base64.NO_WRAP),
                stderr = "timeout after ${timeoutSeconds}s\n${stderr.toString().trimEnd()}".trim(),
                durationMs = System.currentTimeMillis() - started
            )
        }
        stdoutThread.join(1000)
        stderrThread.join(1000)
        ShellResult(
            exitCode = process.exitValue(),
            stdout = Base64.encodeToString(stdout.toByteArray(), Base64.NO_WRAP),
            stderr = stderr.toString().trimEnd(),
            durationMs = System.currentTimeMillis() - started
        )
    }

    suspend fun executeWithBase64Stdin(command: String, dataBase64: String, timeoutSeconds: Long = 60): ShellResult = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val process = startRootProcess() ?: return@withContext ShellResult(
            exitCode = 127,
            stdout = "",
            stderr = "su not found in ${suCandidates.joinToString()}",
            durationMs = System.currentTimeMillis() - started
        )
        val writer = OutputStreamWriter(process.outputStream)
        writer.write(command)
        writer.write("\n")
        writer.flush()
        val bytes = Base64.decode(dataBase64, Base64.DEFAULT)
        process.outputStream.write(bytes)
        process.outputStream.flush()
        process.outputStream.close()

        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val stdoutThread = drain(process.inputStream.reader(), stdout)
        val stderrThread = drain(process.errorStream.reader(), stderr)
        val finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS)
        if (!finished) {
            process.destroyForcibly()
            stdoutThread.join(1000)
            stderrThread.join(1000)
            return@withContext ShellResult(
                exitCode = -1,
                stdout = stdout.toString().trimEnd(),
                stderr = "timeout after ${timeoutSeconds}s\n${stderr.toString().trimEnd()}".trim(),
                durationMs = System.currentTimeMillis() - started
            )
        }
        stdoutThread.join(1000)
        stderrThread.join(1000)
        ShellResult(
            exitCode = process.exitValue(),
            stdout = stdout.toString().trimEnd(),
            stderr = stderr.toString().trimEnd(),
            durationMs = System.currentTimeMillis() - started
        )
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

    private fun startRootProcess(): Process? {
        for (su in suCandidates) {
            try {
                return ProcessBuilder(su).start()
            } catch (_: IOException) {
            }
        }
        return null
    }
}
