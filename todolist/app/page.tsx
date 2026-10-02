import { TaskList } from "@/components/TaskList"
import { TaskInput } from "@/components/TaskInput"
import { ModeToggle } from "@/components/ModeToggle"

export default function Home() {
  return (
    <main className="min-h-screen bg-background p-4 md:p-8 lg:p-12">
      <div className="max-w-3xl mx-auto">
        <header className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Tasks</h1>
            <p className="text-muted-foreground mt-1">Manage your tasks with infinite nesting.</p>
          </div>
          <ModeToggle />
        </header>

        <TaskInput />
        
        <div className="bg-card rounded-xl border shadow-sm p-4 md:p-6">
          <TaskList />
        </div>
      </div>
    </main>
  )
}
