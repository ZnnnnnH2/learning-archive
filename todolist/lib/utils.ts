import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

import { Task } from "@prisma/client"
import { TaskWithChildren } from "./types"

export function buildTaskTree(tasks: Task[]): TaskWithChildren[] {
  const taskMap = new Map<string, TaskWithChildren>()
  const roots: TaskWithChildren[] = []

  // First pass: create TaskWithChildren objects
  tasks.forEach((task) => {
    taskMap.set(task.id, { ...task, children: [] })
  })

  // Second pass: link children to parents
  tasks.forEach((task) => {
    const node = taskMap.get(task.id)!
    if (task.parentId) {
      const parent = taskMap.get(task.parentId)
      if (parent) {
        parent.children.push(node)
      } else {
        // Parent might be deleted or missing, treat as root or orphan
        roots.push(node)
      }
    } else {
      roots.push(node)
    }
  })

  // Sort function to order by sortOrder
  const sortBySortOrder = (a: TaskWithChildren, b: TaskWithChildren) => 
    a.sortOrder - b.sortOrder

  // Recursively sort all children
  const sortChildren = (node: TaskWithChildren) => {
    node.children.sort(sortBySortOrder)
    node.children.forEach(sortChildren)
  }

  // Sort roots and all nested children
  roots.sort(sortBySortOrder)
  roots.forEach(sortChildren)

  return roots
}

