import * as React from "react"

import { cn } from "@/lib/utils"

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * The current progress value (0-100)
   */
  value?: number
  /**
   * Whether the progress bar should show an indeterminate state
   */
  indeterminate?: boolean
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, indeterminate = false, ...props }, ref) => {
    const clampedValue = Math.max(0, Math.min(100, value))

    return (
      <div
        ref={ref}
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full bg-primary/20",
          className
        )}
        {...props}
      >
        <div
          className={cn(
            "h-full bg-primary transition-all duration-300 ease-in-out",
            indeterminate && "animate-indeterminate-progress"
          )}
          style={
            indeterminate
              ? { width: "50%" }
              : { width: `${clampedValue}%` }
          }
        />
      </div>
    )
  }
)
Progress.displayName = "Progress"

export { Progress }
