package com.example.hybridtodo.data.local

import android.content.Context
import com.example.hybridtodo.HybridTodoApp

object CookieStore {
    private const val PREF_NAME = "widget_auth"
    private const val KEY_COOKIE = "cookie"

    private val prefs by lazy {
        HybridTodoApp.instance.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
    }

    fun saveCookie(cookie: String) {
        prefs.edit().putString(KEY_COOKIE, cookie).apply()
    }

    fun getCookie(): String? = prefs.getString(KEY_COOKIE, null)
}
