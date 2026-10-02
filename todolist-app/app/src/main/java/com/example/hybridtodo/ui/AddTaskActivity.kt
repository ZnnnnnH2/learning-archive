package com.example.hybridtodo.ui

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import com.example.hybridtodo.R
import com.example.hybridtodo.databinding.ActivityAddTaskBinding
import com.example.hybridtodo.data.repository.TaskRepository
import com.example.hybridtodo.widget.TodoListWidget
import com.example.hybridtodo.data.remote.RetrofitClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AddTaskActivity : AppCompatActivity() {

    private lateinit var binding: ActivityAddTaskBinding
    private val job = Job()
    private val uiScope = CoroutineScope(Dispatchers.Main + job)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Initialize RetrofitClient (important when launched from widget)
        RetrofitClient.init(applicationContext)
        
        binding = ActivityAddTaskBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnCancel.setOnClickListener { finish() }
        binding.btnSave.setOnClickListener { attemptSave() }
    }

    override fun onDestroy() {
        super.onDestroy()
        job.cancel()
    }

    private fun attemptSave() {
        val title = binding.etTaskTitle.text.toString().trim()
        if (title.isEmpty()) {
            Toast.makeText(this, "请输入标题", Toast.LENGTH_SHORT).show()
            return
        }

        setLoading(true)
        uiScope.launch {
            val success = withContext(Dispatchers.IO) {
                TaskRepository.createTask(title = title)
            }
            setLoading(false)

            if (success) {
                Toast.makeText(this@AddTaskActivity, "创建成功", Toast.LENGTH_SHORT).show()
                notifyWidget()
                finish()
            } else {
                Toast.makeText(this@AddTaskActivity, "创建失败，请稍后重试", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.isVisible = loading
        binding.btnSave.isEnabled = !loading
        binding.btnCancel.isEnabled = !loading
    }

    private fun notifyWidget() {
        val appWidgetManager = AppWidgetManager.getInstance(application)
        val ids = appWidgetManager.getAppWidgetIds(ComponentName(application, TodoListWidget::class.java))
        if (ids.isNotEmpty()) {
            appWidgetManager.notifyAppWidgetViewDataChanged(ids, R.id.widget_list)
        }
    }
}
