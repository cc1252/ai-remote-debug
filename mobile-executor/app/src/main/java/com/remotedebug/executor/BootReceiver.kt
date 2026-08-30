package com.remotedebug.executor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.util.Log

/**
 * 开机 / 应用更新后自动拉起远程调试服务。
 *
 * 仅当用户此前手动启动过(autoStart=true 已持久化)才会自动连，
 * 避免装上就强制联网。配置来自 SharedPreferences + RemoteDebugConfig。
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != Intent.ACTION_LOCKED_BOOT_COMPLETED &&
            action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) {
            return
        }

        val prefs = context.getSharedPreferences("remote-debug", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("autoStart", false)) {
            Log.i(TAG, "autoStart 未开启，跳过开机自启")
            return
        }

        val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        val deviceName = prefs.getString("deviceName", "").orEmpty().ifBlank { android.os.Build.MODEL }
        val relayUrl = prefs.getString("relayUrl", RemoteDebugConfig.DEFAULT_RELAY_URL).orEmpty()
        val token = prefs.getString("token", RemoteDebugConfig.DEFAULT_API_TOKEN).orEmpty()
        if (relayUrl.isBlank() || token.length < 32) {
            Log.w(TAG, "Relay 配置无效，跳过开机自启")
            return
        }

        val serviceIntent = Intent(context, RemoteExecutorService::class.java)
            .putExtra(RemoteExecutorService.EXTRA_RELAY_URL, relayUrl)
            .putExtra(RemoteExecutorService.EXTRA_TOKEN, token)
            .putExtra(RemoteExecutorService.EXTRA_DEVICE_ID, deviceId)
            .putExtra(RemoteExecutorService.EXTRA_DEVICE_NAME, deviceName)

        Log.i(TAG, "开机自启远程调试: $deviceName ($deviceId)")
        try {
            context.startForegroundService(serviceIntent)
        } catch (e: Exception) {
            // targetSdk 34+ 若 App 不在电池优化白名单, 开机后台启动 FGS 会被拒。
            // 退化为普通 startService, 由 service 自己尽快 startForeground。
            Log.w(TAG, "startForegroundService 被拒, 尝试 startService: ${e.message}")
            try {
                context.startService(serviceIntent)
            } catch (e2: Exception) {
                Log.e(TAG, "启动服务失败, 需将 App 加入电池优化白名单: ${e2.message}")
            }
        }
    }

    companion object {
        private const val TAG = "BootReceiver"
    }
}
