package com.remotedebug.executor

import android.os.Build
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class RelayClient(
    private val serviceScope: CoroutineScope,
    private val relayBaseUrl: String,
    private val token: String,
    private val deviceId: String,
    private val deviceName: String,
    private val registry: CommandRegistry,
    private val onStatus: (String) -> Unit
) {
    private val http = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private var socket: WebSocket? = null
    private var heartbeatJob: Job? = null

    fun connect() {
        val url = relayBaseUrl.trimEnd('/') + "/$deviceId"
        Log.i(TAG, "Connecting to: $url")
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .build()
        socket = http.newWebSocket(request, listener)
    }

    fun close() {
        heartbeatJob?.cancel()
        socket?.close(1000, "stopped")
        socket = null
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(TAG, "WebSocket connected")
            onStatus("已连接 Relay")
            sendHello(webSocket)
            heartbeatJob = serviceScope.launch {
                while (true) {
                    delay(15_000)
                    webSocket.send(JSONObject().put("type", "heartbeat").toString())
                }
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val message = JSONObject(text)
            if (message.optString("type") != "command") return

            val requestId = message.getString("requestId")
            val action = message.getString("action")
            val args = message.optJSONObject("args") ?: JSONObject()
            serviceScope.launch(Dispatchers.IO) {
                runCatching { registry.handle(action, args) }
                    .onSuccess { result -> sendResult(webSocket, requestId, "ok", result) }
                    .onFailure { error ->
                        val result = ShellResult(1, "", error.message ?: error.toString(), 0)
                        sendResult(webSocket, requestId, "error", result)
                    }
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "WebSocket failure: ${t.message}", t)
            onStatus("连接失败: ${t.message}")
            heartbeatJob?.cancel()
            serviceScope.launch {
                delay(5_000)
                connect()
            }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            onStatus("连接已关闭: $reason")
            heartbeatJob?.cancel()
        }
    }

    private fun sendHello(webSocket: WebSocket) {
        serviceScope.launch {
            val root = RootShell().hasRoot()
            webSocket.send(
                JSONObject()
                    .put("type", "hello")
                    .put("name", deviceName)
                    .put("model", Build.MODEL)
                    .put("androidVersion", Build.VERSION.RELEASE)
                    .put("root", root)
                    .toString()
            )
        }
    }

    private fun sendResult(webSocket: WebSocket, requestId: String, status: String, result: ShellResult) {
        webSocket.send(
            JSONObject()
                .put("type", "result")
                .put("requestId", requestId)
                .put("status", status)
                .put("exitCode", result.exitCode)
                .put("stdout", result.stdout.take(8 * 1024 * 1024))
                .put("stderr", result.stderr.take(512 * 1024))
                .put("durationMs", result.durationMs)
                .toString()
        )
    }

    companion object {
        private const val TAG = "RelayClient"
    }
}
