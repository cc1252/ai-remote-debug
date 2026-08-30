package com.remotedebug.executor

import android.os.Build
import org.json.JSONObject

class CommandRegistry(
    private val shell: RootShell = RootShell(),
    private val artifactTransfer: ArtifactTransfer = ArtifactTransfer()
) {
    suspend fun handle(action: String, args: JSONObject): ShellResult {
        return when (action) {
            "device.info" -> deviceInfo()
            "logcat.dump" -> shell.execute(logcatCommand(args), root = false, timeoutSeconds = 20)
            "app.list" -> shell.execute("pm list packages", root = false, timeoutSeconds = 20)
            "app.start" -> shell.execute("am start ${required(args, "component")}", root = false, timeoutSeconds = 20)
            "app.stop" -> shell.execute("am force-stop ${required(args, "packageName")}", root = false, timeoutSeconds = 20)
            "app.clearData" -> shell.execute("pm clear ${required(args, "packageName")}", root = true, timeoutSeconds = 30)
            "app.dumpsys" -> shell.execute("dumpsys package ${required(args, "packageName")}", root = true, timeoutSeconds = 30)
            "input.keyevent" -> shell.execute("input keyevent ${required(args, "key")}", root = true, timeoutSeconds = 10)
            "input.tap" -> shell.execute("input tap ${args.getInt("x")} ${args.getInt("y")}", root = true, timeoutSeconds = 10)
            "input.swipe" -> shell.execute("input swipe ${args.getInt("x1")} ${args.getInt("y1")} ${args.getInt("x2")} ${args.getInt("y2")} ${args.optInt("durationMs", 300)}", root = true, timeoutSeconds = 10)
            "input.text" -> shell.execute("input text ${quoteInputText(required(args, "text"))}", root = true, timeoutSeconds = 10)
            "adb.tcp.status" -> shell.execute("getprop service.adb.tcp.port", root = false, timeoutSeconds = 10)
            "adb.tcp.enable" -> shell.execute("setprop service.adb.tcp.port 5555; stop adbd; start adbd; getprop service.adb.tcp.port", root = true, timeoutSeconds = 20)
            "adb.tcp.disable" -> shell.execute("setprop service.adb.tcp.port -1; stop adbd; start adbd; getprop service.adb.tcp.port", root = true, timeoutSeconds = 20)
            "file.readBase64" -> shell.execute("base64 ${required(args, "path")}", root = true, timeoutSeconds = args.optLong("timeoutSeconds", 60))
            "file.writeBase64" -> shell.execute("base64 -d > ${required(args, "path")} <<'ARD_EOF'\n${requiredRaw(args, "data")}\nARD_EOF", root = true, timeoutSeconds = args.optLong("timeoutSeconds", 60))
            "file.stat" -> shell.execute("ls -la ${required(args, "path")}; toybox stat ${required(args, "path")} 2>/dev/null || stat ${required(args, "path")} 2>/dev/null", root = true, timeoutSeconds = 20)
            "file.size" -> shell.execute("wc -c < ${required(args, "path")}", root = true, timeoutSeconds = 20)
            "file.readChunkBase64" -> shell.executeForBase64Stdout(readChunkCommand(args), timeoutSeconds = args.optLong("timeoutSeconds", 60))
            "file.writeChunkBase64" -> shell.executeWithBase64Stdin(writeChunkCommand(args), requiredRaw(args, "data"), timeoutSeconds = args.optLong("timeoutSeconds", 60))
            "app.install" -> shell.execute("pm install -r ${required(args, "path")}", root = true, timeoutSeconds = args.optLong("timeoutSeconds", 120))
            "screen.cap" -> shell.execute("screencap -p | base64", root = shell.hasRoot(), timeoutSeconds = 20)
            "artifact.downloadToFile" -> artifactTransfer.downloadToFile(args)
            "artifact.uploadFromFile" -> artifactTransfer.uploadFromFile(args)
            "shell.exec" -> shell.execute(requiredRaw(args, "command"), root = args.optBoolean("root", true), timeoutSeconds = args.optLong("timeoutSeconds", 30))
            else -> ShellResult(2, "", "unknown action: $action", 0)
        }
    }

    private suspend fun deviceInfo(): ShellResult {
        val root = shell.hasRoot()
        val output = JSONObject()
            .put("model", Build.MODEL)
            .put("manufacturer", Build.MANUFACTURER)
            .put("androidVersion", Build.VERSION.RELEASE)
            .put("sdk", Build.VERSION.SDK_INT)
            .put("root", root)
            .toString(2)
        return ShellResult(0, output, "", 0)
    }

    private fun logcatCommand(args: JSONObject): String {
        val lines = args.optInt("lines", 1000).coerceIn(1, 20000)
        val level = args.optString("level", "")
        val tag = args.optString("tag", "")
        val base = StringBuilder("logcat -d -t $lines")
        if (tag.isNotBlank() && level.isNotBlank()) {
            base.append(" -s ").append(quoteShell(tag)).append(":").append(level)
        }
        return base.toString()
    }

    private fun readChunkCommand(args: JSONObject): String {
        val path = required(args, "path")
        val offset = args.optLong("offset", 0).coerceAtLeast(0)
        val size = args.optInt("size", 512 * 1024).coerceIn(1, 2 * 1024 * 1024)
        val blockSize = 4096L
        val skipBlocks = offset / blockSize
        val skipBytes = offset % blockSize
        val countBlocks = (size + blockSize - 1) / blockSize
        return if (skipBytes == 0L) {
            "dd if=$path bs=$blockSize skip=$skipBlocks count=$countBlocks 2>/dev/null | head -c $size"
        } else {
            "dd if=$path bs=$blockSize skip=$skipBlocks 2>/dev/null | dd bs=1 skip=$skipBytes count=$size 2>/dev/null"
        }
    }

    private fun writeChunkCommand(args: JSONObject): String {
        val path = required(args, "path")
        val append = args.optBoolean("append", true)
        val redirect = if (append) ">>" else ">"
        return "cat $redirect $path"
    }

    private fun required(args: JSONObject, name: String): String {
        val value = args.optString(name, "")
        require(value.isNotBlank()) { "missing argument: $name" }
        return quoteShell(value)
    }

    private fun requiredRaw(args: JSONObject, name: String): String {
        val value = args.optString(name, "")
        require(value.isNotBlank()) { "missing argument: $name" }
        return value
    }

    private fun quoteShell(value: String): String {
        return "'" + value.replace("'", "'\\''") + "'"
    }

    private fun quoteInputText(value: String): String {
        return quoteShell(value.replace(" ", "%s"))
    }
}
