package com.example.hybridtodo.widget

import android.content.Context
import android.content.Intent
import android.os.Binder
import android.util.Log
import android.view.View
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import com.example.hybridtodo.R
import com.example.hybridtodo.data.model.Task
import com.example.hybridtodo.data.repository.TaskRepository
import com.example.hybridtodo.data.remote.RetrofitClient
import kotlinx.coroutines.runBlocking

class WidgetRemoteViewsFactory(private val context: Context) : RemoteViewsService.RemoteViewsFactory {

    private var displayList: List<DisplayTask> = emptyList()

    override fun onCreate() {
        // Initialize data source if needed
    }

    override fun onDataSetChanged() {
        Log.d("WidgetFactory", "onDataSetChanged called")
        
        // Initialize RetrofitClient
        RetrofitClient.init(context)
        
        val prefs = context.getSharedPreferences(WidgetConstants.PREFS_WIDGET, Context.MODE_PRIVATE)
        val hideCompleted = prefs.getBoolean(WidgetConstants.PREF_HIDE_COMPLETED, false)

        val identity = Binder.clearCallingIdentity()
        try {
            // API is public, no cookie required - directly fetch tasks
            runBlocking {
                try {
                    var fetched = TaskRepository.fetchTasks()
                    if (hideCompleted) {
                        fetched = fetched.filter { !it.isCompleted }
                    }
                    displayList = buildDisplayList(fetched)
                    Log.d("WidgetFactory", "Fetched ${displayList.size} tasks for display")
                    if (displayList.isEmpty()) {
                        displayList = listOf(
                            DisplayTask(
                                Task(
                                    id = "empty",
                                    title = "暂无待办事项",
                                    isCompleted = false,
                                    priority = "Low"
                                )
                            )
                        )
                    }
                } catch (e: Exception) {
                    Log.e("WidgetFactory", "Error fetching tasks", e)
                    displayList = listOf(
                        DisplayTask(
                            Task(
                                id = "error_network",
                                title = "网络错误，点击刷新",
                                isCompleted = false,
                                priority = "High"
                            )
                        )
                    )
                }
            }
        } finally {
            Binder.restoreCallingIdentity(identity)
        }
    }

    override fun onDestroy() {
        displayList = emptyList()
    }

    override fun getCount(): Int {
        return displayList.size
    }

    override fun getViewAt(position: Int): RemoteViews {
        Log.d("WidgetFactory", "getViewAt position: $position")
        if (position == -1 || position >= displayList.size) {
            return RemoteViews(context.packageName, R.layout.widget_item)
        }

        val display = displayList[position]
        val task = display.task
        val views = RemoteViews(context.packageName, R.layout.widget_item)

        try {
            val prefix = if (display.depth > 0) "↳ ".repeat(display.depth.coerceAtMost(3)) else ""
            views.setTextViewText(R.id.tv_task_title, prefix + task.title)

            // Set Checkbox Icon
            if (task.isCompleted) {
                views.setImageViewResource(R.id.iv_check, R.drawable.ic_check_filled)
            } else {
                views.setImageViewResource(R.id.iv_check, R.drawable.ic_check_outline)
            }

            // Set Priority Color
            val priorityColor = when (task.priority.lowercase()) {
                "high" -> context.getColor(R.color.priority_high)
                "medium" -> context.getColor(R.color.priority_medium)
                "low" -> context.getColor(R.color.priority_low)
                else -> context.getColor(R.color.teal_200)
            }
            
            views.setInt(R.id.view_priority, "setBackgroundColor", priorityColor)

            // Fill In Intent for Click
            val fillInIntent = Intent().apply {
                putExtra(WidgetConstants.EXTRA_TASK_ID, task.id)
                putExtra(WidgetConstants.EXTRA_TASK_COMPLETED, task.isCompleted)
            }
            views.setOnClickFillInIntent(R.id.widget_item_root, fillInIntent)
            
            Log.d("WidgetFactory", "Successfully prepared view for task: ${task.title}")
        } catch (e: Exception) {
            Log.e("WidgetFactory", "Error in getViewAt for position $position", e)
        }

        return views
    }

    override fun getLoadingView(): RemoteViews {
        // Return a custom loading view
        val views = RemoteViews(context.packageName, R.layout.widget_item)
        views.setTextViewText(R.id.tv_task_title, "加载中...")
        return views
    }

    override fun getViewTypeCount(): Int {
        return 1
    }

    override fun getItemId(position: Int): Long {
        return position.toLong()
    }

    override fun hasStableIds(): Boolean {
        return true
    }

    private fun buildDisplayList(tasks: List<Task>): List<DisplayTask> {
        if (tasks.isEmpty()) return emptyList()

        val tasksById = tasks.associateBy { it.id }
        val childrenMap = tasks.groupBy { it.parentId }

        val display = mutableListOf<DisplayTask>()

        fun addTaskWithChildren(task: Task, depth: Int) {
            display.add(DisplayTask(task, depth))
            childrenMap[task.id]?.forEach { child ->
                addTaskWithChildren(child, depth + 1)
            }
        }

        val roots = tasks.filter { it.parentId == null || !tasksById.containsKey(it.parentId) }
        roots.forEach { addTaskWithChildren(it, 0) }

        // Edge case: tasks whose parent is in list but came earlier are already included above.
        // If anything is left out (cycle), append it as root to avoid missing entries.
        if (display.size < tasks.size) {
            tasks.forEach { if (!display.any { existing -> existing.task.id == it.id }) display.add(DisplayTask(it, 0)) }
        }

        return display
    }
}

data class DisplayTask(
    val task: Task,
    val depth: Int = 0
)
