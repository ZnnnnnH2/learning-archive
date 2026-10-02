"use server"

import { prisma } from "@/lib/prisma"
import { revalidatePath } from "next/cache"
import { addDays, addWeeks, addMonths } from "date-fns"

export async function getTasks() {
  return await prisma.task.findMany({
    orderBy: [{ sortOrder: "asc" }, { createdAt: "desc" }],
  })
}

export async function createTask(
  title: string,
  parentId?: string | null,
  priority: string = "Medium",
  dueDate?: Date | null,
  isRecurring: boolean = false,
  recurringInterval?: number | null,
  recurringUnit?: string | null
) {
  if (!title) return

  // Get the max sortOrder for tasks with the same parent
  const maxSortOrder = await prisma.task.aggregate({
    where: { parentId: parentId || null },
    _max: { sortOrder: true },
  })
  const newSortOrder = (maxSortOrder._max.sortOrder ?? -1) + 1

  await prisma.task.create({
    data: {
      title,
      parentId: parentId || null,
      priority,
      dueDate: dueDate || null,
      isRecurring,
      recurringInterval: recurringInterval || null,
      recurringUnit: recurringUnit || null,
      sortOrder: newSortOrder,
    },
  })

  revalidatePath("/")
}

function getNextDueDate(currentDueDate: Date, interval: number, unit: string): Date {
  switch (unit) {
    case "day":
      return addDays(currentDueDate, interval)
    case "week":
      return addWeeks(currentDueDate, interval)
    case "month":
      return addMonths(currentDueDate, interval)
    default:
      return addDays(currentDueDate, interval)
  }
}

export async function updateTaskStatus(id: string, isCompleted: boolean) {
  // First get the task to check if it's recurring
  const task = await prisma.task.findUnique({
    where: { id },
  })

  if (!task) return

  // Update the current task status
  await prisma.task.update({
    where: { id },
    data: { isCompleted },
  })

  // If completing a recurring task, create a new task
  if (isCompleted && task.isRecurring && task.recurringInterval && task.recurringUnit) {
    const baseDueDate = task.dueDate || new Date()
    const nextDueDate = getNextDueDate(baseDueDate, task.recurringInterval, task.recurringUnit)

    await prisma.task.create({
      data: {
        title: task.title,
        description: task.description,
        priority: task.priority,
        dueDate: nextDueDate,
        isRecurring: task.isRecurring,
        recurringInterval: task.recurringInterval,
        recurringUnit: task.recurringUnit,
        parentId: task.parentId,
        isCompleted: false,
      },
    })
  }

  revalidatePath("/")
}

export async function updateTaskDetails(
  id: string,
  title: string,
  priority: string,
  dueDate?: Date | null,
  isRecurring?: boolean,
  recurringInterval?: number | null,
  recurringUnit?: string | null
) {
  await prisma.task.update({
    where: { id },
    data: {
      title,
      priority,
      dueDate: dueDate !== undefined ? dueDate : undefined,
      isRecurring: isRecurring !== undefined ? isRecurring : undefined,
      recurringInterval: recurringInterval !== undefined ? recurringInterval : undefined,
      recurringUnit: recurringUnit !== undefined ? recurringUnit : undefined,
    },
  })
  revalidatePath("/")
}

export async function deleteTask(id: string) {
  await prisma.task.delete({
    where: { id },
  })
  revalidatePath("/")
}

export async function reorderTasks(
  orderedIds: string[],
  parentId: string | null = null
) {
  // Batch update all tasks with new sortOrder values
  await Promise.all(
    orderedIds.map((id, index) =>
      prisma.task.update({
        where: { id },
        data: { sortOrder: index },
      })
    )
  )
  revalidatePath("/")
}
