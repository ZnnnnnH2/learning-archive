package com.example.hybridtodo.ui

import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.example.hybridtodo.R
import com.example.hybridtodo.databinding.ActivityMainBinding
import android.content.Context
import android.content.Intent
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import com.example.hybridtodo.widget.TodoListWidget
import com.example.hybridtodo.data.local.CookieStore

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupWebView()
    }

    private fun setupWebView() {
        // Enable cookies for WebView BEFORE loading URL
        val cookieManager = android.webkit.CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(binding.webview, true)
        
        binding.webview.apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            
            // Ensure links open within the WebView
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: android.webkit.WebResourceRequest?): Boolean {
                    // Check for cookies on every navigation
                    saveCookiesIfAvailable(request?.url?.toString())
                    return false // Let WebView handle the URL
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    android.util.Log.d("MainActivity", "=== onPageFinished ===")
                    android.util.Log.d("MainActivity", "URL: $url")
                    
                    saveCookiesIfAvailable(url)
                }
                
                override fun doUpdateVisitedHistory(view: WebView?, url: String?, isReload: Boolean) {
                    super.doUpdateVisitedHistory(view, url, isReload)
                    // This is called when URL changes (e.g., after login redirect)
                    android.util.Log.d("MainActivity", "=== doUpdateVisitedHistory ===")
                    android.util.Log.d("MainActivity", "URL: $url, isReload: $isReload")
                    saveCookiesIfAvailable(url)
                }
            }

            // Load the Next.js app URL
            android.util.Log.d("MainActivity", "Loading URL: http://20.193.248.140/")
            loadUrl("http://20.193.248.140/")
        }
    }
    
    private fun saveCookiesIfAvailable(url: String?) {
        if (url == null) return
        
        android.webkit.CookieManager.getInstance().flush()
        val cookie = android.webkit.CookieManager.getInstance().getCookie(url)
        android.util.Log.d("MainActivity", "Checking cookies for URL: $url")
        android.util.Log.d("MainActivity", "Cookie: ${cookie?.take(100) ?: "NULL"}")
        
        if (!cookie.isNullOrEmpty()) {
            val prefs = getSharedPreferences("widget_auth", Context.MODE_PRIVATE)
            val existingCookie = prefs.getString("cookie", null)
            
            // Only save if cookie is different (new login or updated)
            if (cookie != existingCookie) {
                val success = prefs.edit().putString("cookie", cookie).commit()
                android.util.Log.d("MainActivity", "NEW Cookie saved! Success: $success")
                android.util.Log.d("MainActivity", "Cookie content: ${cookie.take(100)}")
                
                CookieStore.saveCookie(cookie)

                // Notify Widget to refresh
                val appWidgetManager = AppWidgetManager.getInstance(application)
                val ids = appWidgetManager.getAppWidgetIds(ComponentName(application, TodoListWidget::class.java))
                android.util.Log.d("MainActivity", "Notifying ${ids.size} widgets to refresh")
                appWidgetManager.notifyAppWidgetViewDataChanged(ids, R.id.widget_list)
            }
        }
    }

    override fun onBackPressed() {
        if (binding.webview.canGoBack()) {
            binding.webview.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
