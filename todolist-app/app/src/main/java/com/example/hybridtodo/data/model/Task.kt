package com.example.hybridtodo.data.model

import com.google.gson.annotations.SerializedName

data class Task(
    val id: String = "",
    val title: String = "",
    val isCompleted: Boolean = false,
    val priority: String = "Medium",
    val description: String? = null,
    val createdAt: String? = null,
    val parentId: String? = null
)

data class ToggleTaskRequest(
    val id: String,
    val isCompleted: Boolean
)

data class BasicResponse(
    val success: Boolean
)

data class CreateTaskRequest(
    val title: String,
    val description: String? = null,
    val priority: String = "Medium",
    val parentId: String? = null
)
