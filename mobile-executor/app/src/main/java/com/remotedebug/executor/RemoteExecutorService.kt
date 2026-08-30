package com.remotedebug.executor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

class RemoteExecutorService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var client: RelayClient? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val relayUrl = intent?.getStringExtra(EXTRA_RELAY_URL).orEmpty()
        val token = intent?.getStringExtra(EXTRA_TOKEN).orEmpty()
        val deviceId = intent?.getStringExtra(EXTRA_DEVICE_ID).orEmpty()
        val deviceName = intent?.getStringExtra(EXTRA_DEVICE_NAME).orEmpty().ifBlank { Build.MODEL }
        if (relayUrl.isBlank() || token.isBlank() || deviceId.isBlank()) {
            stopSelf()
            return START_NOT_STICKY
        }

        startForeground(NOTIFICATION_ID, notification("正在连接 Relay"))
        client?.close()
        client = RelayClient(
            serviceScope = scope,
            relayBaseUrl = relayUrl,
            token = token,
            deviceId = deviceId,
            deviceName = deviceName,
            registry = CommandRegistry(),
            onStatus = { status -> updateNotification(status) }
        ).also { it.connect() }
        return START_STICKY
    }

    override fun onDestroy() {
        client?.close()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Remote Debug Executor", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun updateNotification(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("远程调试执行器")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("远程调试执行器")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setOngoing(true)
                .build()
        }
    }

    companion object {
        const val EXTRA_RELAY_URL = "relayUrl"
        const val EXTRA_TOKEN = "token"
        const val EXTRA_DEVICE_ID = "deviceId"
        const val EXTRA_DEVICE_NAME = "deviceName"
        private const val CHANNEL_ID = "remote_debug_executor"
        private const val NOTIFICATION_ID = 1001
    }
}
