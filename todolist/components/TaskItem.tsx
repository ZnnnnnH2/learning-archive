"use client"

import { useState, useRef, useEffect } from "react"
import { TaskWithChildren } from "@/lib/types"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ChevronRight, ChevronDown, Plus, Trash2, Clock, Repeat, CalendarDays, GripVertical } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"
import { updateTaskStatus, deleteTask, createTask, updateTaskDetails } from "@/app/actions/task"
import { useQueryClient, useMutation } from "@tanstack/react-query"
import { formatDistanceToNow, format, isPast, isToday, startOfDay } from "date-fns"

interface TaskItemProps {
  task: TaskWithChildren
  level?: number
  dragListeners?: React.HTMLAttributes<HTMLButtonElement>
}

export function TaskItem({ task, level = 0, dragListeners }: TaskItemProps) {
  const [isOpen, setIsOpen] = useState(true)
  const [isAddingSubtask, setIsAddingSubtask] = useState(false)
  const [newSubtaskTitle, setNewSubtaskTitle] = useState("")
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(task.title)
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isEditing])

  // Check if task is overdue
  const isOverdue = task.dueDate && !task.isCompleted && isPast(startOfDay(new Date(task.dueDate))) && !isToday(new Date(task.dueDate))
  const isDueToday = task.dueDate && isToday(new Date(task.dueDate))

  // Optimistic Toggle
  const { mutate: toggleTask } = useMutation({
    mutationFn: async (checked: boolean) => {
      await updateTaskStatus(task.id, checked)
    },
    onMutate: async (checked) => {
      await queryClient.cancelQueries({ queryKey: ["tasks"] })
      const previousTasks = queryClient.getQueryData(["tasks"])
      
      queryClient.setQueryData(["tasks"], (old: any[]) => {
        return old.map((t) => t.id === task.id ? { ...t, isCompleted: checked } : t)
      })

      return { previousTasks }
    },
    onError: (err, newTodo, context) => {
      queryClient.setQueryData(["tasks"], context?.previousTasks)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })

  // Optimistic Delete
  const { mutate: removeTask } = useMutation({
    mutationFn: async () => {
      await deleteTask(task.id)
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["tasks"] })
      const previousTasks = queryClient.getQueryData(["tasks"])
      
      queryClient.setQueryData(["tasks"], (old: any[]) => {
        return old.filter((t) => t.id !== task.id)
      })

      return { previousTasks }
    },
    onError: (err, newTodo, context) => {
      queryClient.setQueryData(["tasks"], context?.previousTasks)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })

  // Optimistic Edit
  const { mutate: saveEdit } = useMutation({
    mutationFn: async (newTitle: string) => {
      if (newTitle === task.title) return
      await updateTaskDetails(task.id, newTitle, task.priority)
    },
    onMutate: async (newTitle) => {
      await queryClient.cancelQueries({ queryKey: ["tasks"] })
      const previousTasks = queryClient.getQueryData(["tasks"])
      
      queryClient.setQueryData(["tasks"], (old: any[]) => {
        return old.map((t) => t.id === task.id ? { ...t, title: newTitle } : t)
      })

      return { previousTasks }
    },
    onError: (err, newTodo, context) => {
      queryClient.setQueryData(["tasks"], context?.previousTasks)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })

  const handleAddSubtask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSubtaskTitle.trim()) return
    await createTask(newSubtaskTitle, task.id)
    setNewSubtaskTitle("")
    setIsAddingSubtask(false)
    setIsOpen(true)
    queryClient.invalidateQueries({ queryKey: ["tasks"] })
  }

  const handleEditSubmit = () => {
    if (!editTitle.trim()) {
      setEditTitle(task.title)
      setIsEditing(false)
      return
    }
    saveEdit(editTitle)
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleEditSubmit()
    if (e.key === "Escape") {
      setEditTitle(task.title)
      setIsEditing(false)
    }
  }

  const getBadgeStyle = (p: string) => {
    switch (p) {
      case "High": return "bg-red-500/10 text-red-600 hover:bg-red-500/20 border-red-200 dark:border-red-900"
      case "Medium": return "bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20 border-yellow-200 dark:border-yellow-900"
      case "Low": return "bg-blue-500/10 text-blue-600 hover:bg-blue-500/20 border-blue-200 dark:border-blue-900"
      default: return ""
    }
  }

  const getRecurringLabel = (unit: string | null) => {
    switch (unit) {
      case "day": return "Daily"
      case "week": return "Weekly"
      case "month": return "Monthly"
      default: return ""
    }
  }

  const completedChildren = task.children.filter(c => c.isCompleted).length
  const totalChildren = task.children.length
  const progress = totalChildren > 0 ? Math.round((completedChildren / totalChildren) * 100) : 0

  return (
    <div className="w-full">
      <motion.div
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className={cn(
          "group flex items-center gap-3 p-3 rounded-lg hover:bg-accent/50 transition-all duration-200 border border-transparent hover:border-border/50",
          task.isCompleted && "opacity-60 bg-accent/20"
        )}
        style={{ marginLeft: `${level * 1.5}rem` }}
      >
        {/* Drag Handle */}
        {dragListeners && (
          <button
            {...dragListeners}
            className="h-6 w-6 shrink-0 flex items-center justify-center text-muted-foreground/50 hover:text-muted-foreground cursor-grab active:cursor-grabbing touch-none"
          >
            <GripVertical className="h-4 w-4" />
          </button>
        )}

        <Button
          variant="ghost"
          size="icon"
          className={cn("h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground transition-colors", task.children.length === 0 && "invisible")}
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>

        <Checkbox
          checked={task.isCompleted}
          onCheckedChange={(c) => toggleTask(c as boolean)}
          className="rounded-full data-[state=checked]:bg-primary data-[state=checked]:border-primary transition-all duration-300"
        />

        <div className="flex-1 flex flex-col min-w-0">
          {isEditing ? (
            <Input
              ref={inputRef}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onBlur={handleEditSubmit}
              onKeyDown={handleKeyDown}
              className="h-6 py-0 px-1 text-base border-none focus-visible:ring-0 bg-transparent -ml-1"
            />
          ) : (
            <span 
              onDoubleClick={() => setIsEditing(true)}
              className={cn(
                "font-medium transition-all duration-300 cursor-text truncate select-none", 
                task.isCompleted && "line-through text-muted-foreground"
              )}
            >
              {task.title}
            </span>
          )}
          
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1.5 flex-wrap">
             <Badge variant="outline" className={cn("font-medium px-2 py-0.5 text-[10px] uppercase tracking-wider border", getBadgeStyle(task.priority))}>
                {task.priority}
             </Badge>
             
             <span className="flex items-center gap-1.5" title={new Date(task.createdAt).toLocaleString()}>
                <Clock className="h-3 w-3" />
                {formatDistanceToNow(new Date(task.createdAt), { addSuffix: true })}
             </span>

             {/* Due Date Badge */}
             {task.dueDate && (
               <Badge 
                 variant="outline" 
                 className={cn(
                   "font-medium px-2 py-0.5 text-[10px] uppercase tracking-wider border flex items-center gap-1",
                   isOverdue && "bg-red-500/10 text-red-600 border-red-200 dark:border-red-900",
                   isDueToday && !isOverdue && "bg-orange-500/10 text-orange-600 border-orange-200 dark:border-orange-900",
                   !isOverdue && !isDueToday && "bg-purple-500/10 text-purple-600 border-purple-200 dark:border-purple-900"
                 )}
               >
                 <CalendarDays className="h-3 w-3" />
                 {isOverdue ? "Overdue" : isDueToday ? "Today" : format(new Date(task.dueDate), "MMM d")}
               </Badge>
             )}

             {/* Recurring Badge */}
             {task.isRecurring && task.recurringUnit && (
               <Badge 
                 variant="outline" 
                 className="font-medium px-2 py-0.5 text-[10px] uppercase tracking-wider border bg-cyan-500/10 text-cyan-600 border-cyan-200 dark:border-cyan-900 flex items-center gap-1"
               >
                 <Repeat className="h-3 w-3" />
                 {getRecurringLabel(task.recurringUnit)}
               </Badge>
             )}

             {totalChildren > 0 && (
               <span className="flex items-center gap-1.5 text-xs font-medium">
                 <div className="h-1.5 w-12 bg-secondary rounded-full overflow-hidden">
                   <div 
                     className="h-full bg-primary transition-all duration-500 ease-out" 
                     style={{ width: `${progress}%` }}
                   />
                 </div>
                 <span className="text-[10px]">{completedChildren}/{totalChildren}</span>
               </span>
             )}
          </div>
        </div>

        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-background hover:shadow-sm" onClick={() => setIsAddingSubtask(!isAddingSubtask)}>
                <Plus className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10" onClick={() => removeTask()}>
                <Trash2 className="h-4 w-4" />
            </Button>
        </div>
      </motion.div>

      <AnimatePresence>
        {isAddingSubtask && (
            <motion.form
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                onSubmit={handleAddSubtask}
                className="pl-12 pr-4 py-2"
                style={{ marginLeft: `${level * 1.5}rem` }}
            >
                <div className="flex gap-2">
                    <Input
                        autoFocus
                        placeholder="Subtask title..."
                        value={newSubtaskTitle}
                        onChange={(e) => setNewSubtaskTitle(e.target.value)}
                        className="h-9 bg-background"
                    />
                    <Button type="submit" size="sm" variant="secondary">Add</Button>
                </div>
            </motion.form>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isOpen && task.children.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            {task.children.map((child) => (
              <TaskItem key={child.id} task={child} level={level + 1} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
