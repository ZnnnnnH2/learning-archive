package com.example.hybridtodo

import android.app.Application

class HybridTodoApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
        com.example.hybridtodo.data.remote.RetrofitClient.init(this)
    }

    companion object {
        lateinit var instance: HybridTodoApp
            private set
    }
}
