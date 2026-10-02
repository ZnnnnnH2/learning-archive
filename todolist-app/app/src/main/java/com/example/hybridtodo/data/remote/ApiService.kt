package com.example.hybridtodo.data.remote

import com.example.hybridtodo.data.model.BasicResponse
import com.example.hybridtodo.data.model.CreateTaskRequest
import com.example.hybridtodo.data.model.Task
import com.example.hybridtodo.data.model.ToggleTaskRequest
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface ApiService {
    @GET("api/tasks")
    suspend fun getTasks(): List<Task>

    @POST("api/tasks/toggle")
    suspend fun toggleTask(@Body request: ToggleTaskRequest): Response<BasicResponse>

    @POST("api/tasks")
    suspend fun createTask(@Body request: CreateTaskRequest): Response<ResponseBody>
}
