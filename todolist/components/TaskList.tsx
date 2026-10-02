"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { SortableTaskItem } from "./SortableTaskItem"
import { buildTaskTree } from "@/lib/utils"
import { Task } from "@prisma/client"
import { Loader2, Filter } from "lucide-react"
import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { AnimatePresence } from "framer-motion"
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable'
import { reorderTasks } from "@/app/actions/task"
import { TaskWithChildren } from "@/lib/types"

export function TaskList() {
  const [hideCompleted, setHideCompleted] = useState(false)
  const queryClient = useQueryClient()
  
  const { data: tasks, isLoading, error } = useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: async () => {
      const res = await fetch("/api/tasks")
      if (!res.ok) throw new Error("Failed to fetch tasks")
      return res.json()
    },
  })

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 8px movement required before drag starts
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const reorderMutation = useMutation({
    mutationFn: async ({ orderedIds, parentId }: { orderedIds: string[], parentId: string | null }) => {
      await reorderTasks(orderedIds, parentId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })

  const tree = useMemo(() => {
    if (!tasks) return []
    return buildTaskTree(tasks)
  }, [tasks])

  const filteredTree = useMemo(() => {
    if (!hideCompleted) return tree
    
    const filterNodes = (nodes: TaskWithChildren[]): TaskWithChildren[] => {
      return nodes
        .filter(node => !node.isCompleted)
        .map(node => ({
          ...node,
          children: filterNodes(node.children)
        }))
    }
    
    return filterNodes(tree)
  }, [tree, hideCompleted])

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = filteredTree.findIndex(task => task.id === active.id)
      const newIndex = filteredTree.findIndex(task => task.id === over.id)
      
      if (oldIndex !== -1 && newIndex !== -1) {
        const newOrder = arrayMove(filteredTree, oldIndex, newIndex)
        const orderedIds = newOrder.map(task => task.id)
        
        // Optimistic update
        queryClient.setQueryData(["tasks"], (old: Task[] | undefined) => {
          if (!old) return old
          return old.map(task => {
            const newSortOrder = orderedIds.indexOf(task.id)
            if (newSortOrder !== -1 && task.parentId === null) {
              return { ...task, sortOrder: newSortOrder }
            }
            return task
          })
        })
        
        reorderMutation.mutate({ orderedIds, parentId: null })
      }
    }
  }

  if (isLoading) {
    return <div className="flex justify-center p-8"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
  }

  if (error) {
    return <div className="text-destructive text-center p-4">Failed to load tasks</div>
  }

  if (!tasks || tasks.length === 0) {
    return <div className="text-center text-muted-foreground p-8">No tasks yet. Add one above!</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button 
          variant={hideCompleted ? "secondary" : "ghost"} 
          size="sm" 
          onClick={() => setHideCompleted(!hideCompleted)}
          className="gap-2 text-xs"
        >
          <Filter className="h-3.5 w-3.5" />
          {hideCompleted ? "Show Completed" : "Hide Completed"}
        </Button>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={filteredTree.map(task => task.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-1">
            <AnimatePresence mode="popLayout">
              {filteredTree.map((task) => (
                <SortableTaskItem key={task.id} task={task} />
              ))}
            </AnimatePresence>
            
            {filteredTree.length === 0 && hideCompleted && (
              <div className="text-center text-muted-foreground py-8 text-sm">
                All active tasks completed! 🎉
              </div>
            )}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  )
}
