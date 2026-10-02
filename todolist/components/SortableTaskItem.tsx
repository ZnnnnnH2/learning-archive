"use client"

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { TaskWithChildren } from "@/lib/types"
import { TaskItem } from "./TaskItem"

interface SortableTaskItemProps {
  task: TaskWithChildren
  level?: number
}

export function SortableTaskItem({ task, level = 0 }: SortableTaskItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: task.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <TaskItem task={task} level={level} dragListeners={listeners} />
    </div>
  )
}
