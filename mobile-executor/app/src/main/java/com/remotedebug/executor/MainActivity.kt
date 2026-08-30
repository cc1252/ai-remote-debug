package com.remotedebug.executor

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val prefs = getSharedPreferences("remote-debug", MODE_PRIVATE)
        val defaultDeviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
        val statusText = findViewById<TextView>(R.id.statusText)
        val deviceInfoText = findViewById<TextView>(R.id.deviceInfoText)
        val deviceNameInput = findViewById<EditText>(R.id.deviceNameInput)
        val relayUrlInput = findViewById<EditText>(R.id.relayUrlInput)
        val tokenInput = findViewById<EditText>(R.id.tokenInput)

        deviceNameInput.setText(prefs.getString("deviceName", ""))
        relayUrlInput.setText(prefs.getString("relayUrl", RemoteDebugConfig.DEFAULT_RELAY_URL))
        tokenInput.setText(prefs.getString("token", RemoteDebugConfig.DEFAULT_API_TOKEN))
        deviceInfoText.text = "设备ID: $defaultDeviceId\nAndroid: ${android.os.Build.VERSION.RELEASE}\n型号: ${android.os.Build.MODEL}"

        findViewById<Button>(R.id.startButton).setOnClickListener {
            val deviceName = deviceNameInput.text.toString().trim().ifBlank { android.os.Build.MODEL }
            val relayUrl = relayUrlInput.text.toString().trim().trimEnd('/')
            val token = tokenInput.text.toString()
            if (!relayUrl.startsWith("ws://") && !relayUrl.startsWith("wss://")) {
                statusText.text = "Relay 地址必须以 ws:// 或 wss:// 开头"
                return@setOnClickListener
            }
            if (token.length < 32 || token == "replace-with-relay-token") {
                statusText.text = "请填写至少 32 个字符的随机 Relay token"
                return@setOnClickListener
            }
            prefs.edit()
                .putString("deviceName", deviceName)
                .putString("relayUrl", relayUrl)
                .putString("token", token)
                .putBoolean("autoStart", true)
                .apply()
            requestIgnoreBatteryOptimizations()
            startExecutor(relayUrl, token, defaultDeviceId, deviceName)
            val batteryHint = if (isIgnoringBatteryOptimizations()) "" else "\n⚠ 请允许『忽略电池优化』并在系统设置开启『自启动』，否则开机自启可能失效"
            statusText.text = "远程调试已启动(已开启开机自启)\n名称: $deviceName\n设备ID: $defaultDeviceId\n请使用 ard devices 查看在线状态$batteryHint"
        }

        findViewById<Button>(R.id.stopButton).setOnClickListener {
            prefs.edit().putBoolean("autoStart", false).apply()
            stopService(Intent(this, RemoteExecutorService::class.java))
            statusText.text = "已停止远程调试(已关闭开机自启)"
        }
    }

    private fun isIgnoringBatteryOptimizations(): Boolean {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    @Suppress("BatteryLife")
    private fun requestIgnoreBatteryOptimizations() {
        if (isIgnoringBatteryOptimizations()) return
        runCatching {
            startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    .setData(Uri.parse("package:$packageName"))
            )
        }
    }

    private fun startExecutor(relayUrl: String, token: String, deviceId: String, deviceName: String) {
        val intent = Intent(this, RemoteExecutorService::class.java)
            .putExtra(RemoteExecutorService.EXTRA_RELAY_URL, relayUrl)
            .putExtra(RemoteExecutorService.EXTRA_TOKEN, token)
            .putExtra(RemoteExecutorService.EXTRA_DEVICE_ID, deviceId)
            .putExtra(RemoteExecutorService.EXTRA_DEVICE_NAME, deviceName)
        startForegroundService(intent)
    }
}
