import { getTasks, createTask, updateTaskStatus, reorderTasks } from "@/app/actions/task"
import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

// Helper: 设置 CORS 头
function setCorsHeaders(res: NextResponse) {
  res.headers.set('Access-Control-Allow-Origin', '*')
  res.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
  res.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  return res
}

// 处理 OPTIONS 预检请求
export async function OPTIONS() {
  return setCorsHeaders(new NextResponse(null, { status: 204 }))
}

export async function GET() {
  const tasks = await getTasks()
  return setCorsHeaders(NextResponse.json(tasks))
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { action } = body

    if (action === 'create') {
      const { title, priority, dueDate, isRecurring, recurringInterval, recurringUnit } = body
      
      if (!title) {
        return setCorsHeaders(
          NextResponse.json({ error: 'Title is required' }, { status: 400 })
        )
      }

      await createTask(
        title,
        null, // parentId
        priority || 'Medium',
        dueDate ? new Date(dueDate) : null,
        isRecurring || false,
        recurringInterval || null,
        recurringUnit || null
      )

      return setCorsHeaders(
        NextResponse.json({ success: true, message: 'Task created successfully' })
      )
    }

    if (action === 'updateStatus') {
      const { id, isCompleted } = body

      if (!id || isCompleted === undefined) {
        return setCorsHeaders(
          NextResponse.json({ error: 'id and isCompleted are required' }, { status: 400 })
        )
      }

      await updateTaskStatus(id, isCompleted)

      return setCorsHeaders(
        NextResponse.json({ success: true, message: 'Task status updated successfully' })
      )
    }

    if (action === 'reorder') {
      const { orderedIds, parentId } = body

      if (!orderedIds || !Array.isArray(orderedIds)) {
        return setCorsHeaders(
          NextResponse.json({ error: 'orderedIds array is required' }, { status: 400 })
        )
      }

      await reorderTasks(orderedIds, parentId || null)

      return setCorsHeaders(
        NextResponse.json({ success: true, message: 'Tasks reordered successfully' })
      )
    }

    return setCorsHeaders(
      NextResponse.json({ error: 'Invalid action. Use "create", "updateStatus", or "reorder"' }, { status: 400 })
    )

  } catch (error) {
    console.error('API Error:', error)
    return setCorsHeaders(
      NextResponse.json({ error: 'Internal server error' }, { status: 500 })
    )
  }
}
