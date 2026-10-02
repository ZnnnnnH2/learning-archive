package com.example.hybridtodo.data.remote

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import android.content.Context

object RetrofitClient {
    private const val BASE_URL = "http://20.193.248.140/" // Replace with actual URL

    private var appContext: Context? = null

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    private val loggingInterceptor by lazy {
        HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
    }

    // Cookie Interceptor - optional for authenticated APIs
    private val cookieInterceptor by lazy {
        okhttp3.Interceptor { chain ->
            val original = chain.request()
            val requestBuilder = original.newBuilder()
            
            // Try to add cookie if available (for future authenticated APIs)
            appContext?.let { ctx ->
                val prefs = ctx.getSharedPreferences("widget_auth", Context.MODE_PRIVATE)
                val cookie = prefs.getString("cookie", null)
                if (!cookie.isNullOrEmpty()) {
                    requestBuilder.addHeader("Cookie", cookie)
                    android.util.Log.d("RetrofitClient", "Added cookie to request")
                }
            }
            
            chain.proceed(requestBuilder.build())
        }
    }

    // Lazy initialization ensures init() is called first
    private val okHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(loggingInterceptor)
            .addInterceptor(cookieInterceptor)
            .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
            .build()
    }

    val apiService: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
