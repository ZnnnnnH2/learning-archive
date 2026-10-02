"use client"

import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Calendar } from "@/components/ui/calendar"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { createTask } from "@/app/actions/task"
import { useQueryClient } from "@tanstack/react-query"
import { Plus, CalendarIcon, Repeat, ChevronDown } from "lucide-react"
import { format } from "date-fns"
import { cn } from "@/lib/utils"

type RecurringOption = "none" | "daily" | "weekly" | "monthly"

export function TaskInput() {
  const [title, setTitle] = useState("")
  const [priority, setPriority] = useState("Medium")
  const [dueDate, setDueDate] = useState<Date | undefined>(undefined)
  const [recurringOption, setRecurringOption] = useState<RecurringOption>("none")
  const [isOptionsOpen, setIsOptionsOpen] = useState(false)
  const queryClient = useQueryClient()

  const getRecurringValues = (option: RecurringOption) => {
    switch (option) {
      case "daily":
        return { isRecurring: true, interval: 1, unit: "day" }
      case "weekly":
        return { isRecurring: true, interval: 1, unit: "week" }
      case "monthly":
        return { isRecurring: true, interval: 1, unit: "month" }
      default:
        return { isRecurring: false, interval: null, unit: null }
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return

    const { isRecurring, interval, unit } = getRecurringValues(recurringOption)
    
    await createTask(
      title,
      null,
      priority,
      dueDate || null,
      isRecurring,
      interval,
      unit
    )
    
    setTitle("")
    setPriority("Medium")
    setDueDate(undefined)
    setRecurringOption("none")
    setIsOptionsOpen(false)
    queryClient.invalidateQueries({ queryKey: ["tasks"] })
  }

  const hasOptions = dueDate || recurringOption !== "none"

  return (
    <div className="mb-6">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          placeholder="Add a new task..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="flex-1"
        />
        <Select value={priority} onValueChange={setPriority}>
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Low">Low</SelectItem>
            <SelectItem value="Medium">Medium</SelectItem>
            <SelectItem value="High">High</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit">
          <Plus className="h-4 w-4 mr-2" />
          Add
        </Button>
      </form>

      <Collapsible open={isOptionsOpen} onOpenChange={setIsOptionsOpen}>
        <CollapsibleTrigger asChild>
          <Button 
            variant="ghost" 
            size="sm" 
            className={cn(
              "mt-2 text-muted-foreground hover:text-foreground",
              hasOptions && "text-primary"
            )}
          >
            <CalendarIcon className="h-4 w-4 mr-2" />
            {hasOptions ? (
              <span className="flex items-center gap-2">
                {dueDate && format(dueDate, "MMM d, yyyy")}
                {recurringOption !== "none" && (
                  <span className="flex items-center gap-1">
                    <Repeat className="h-3 w-3" />
                    {recurringOption}
                  </span>
                )}
              </span>
            ) : (
              "Set due date & repeat"
            )}
            <ChevronDown className={cn(
              "h-4 w-4 ml-2 transition-transform",
              isOptionsOpen && "rotate-180"
            )} />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3">
          <div className="flex flex-wrap gap-4 p-4 rounded-lg border bg-card">
            {/* Due Date Picker */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-muted-foreground">Due Date</label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-[200px] justify-start text-left font-normal",
                      !dueDate && "text-muted-foreground"
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {dueDate ? format(dueDate, "PPP") : "Pick a date"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={dueDate}
                    onSelect={setDueDate}
                  />
                </PopoverContent>
              </Popover>
              {dueDate && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-fit text-xs text-muted-foreground"
                  onClick={() => setDueDate(undefined)}
                >
                  Clear date
                </Button>
              )}
            </div>

            {/* Repeat Options */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-muted-foreground">Repeat</label>
              <Select value={recurringOption} onValueChange={(v) => setRecurringOption(v as RecurringOption)}>
                <SelectTrigger className="w-[150px]">
                  <Repeat className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Repeat" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No Repeat</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
