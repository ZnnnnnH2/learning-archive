import { Task } from "@prisma/client"

export type TaskWithChildren = Task & {
  children: TaskWithChildren[]
}
