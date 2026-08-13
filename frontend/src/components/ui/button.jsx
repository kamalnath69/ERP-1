import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";
import { SpinnerGap } from "@phosphor-icons/react";
import { useFormContext } from "react-hook-form";

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold transition-[background-color,color,border-color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-card text-foreground shadow-sm hover:border-foreground/15 hover:bg-secondary",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/75",
        ghost: "text-muted-foreground hover:bg-secondary hover:text-foreground",
        link: "h-auto text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-lg px-3 text-xs",
        lg: "h-11 px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({
  className, variant, size, asChild = false, loading = false, loadingText, disabled, children, onClick, ...props
}, ref) => {
  const Comp = asChild ? Slot : "button"
  const form = useFormContext()
  const [actionPending, setActionPending] = React.useState(false)
  const actionPendingRef = React.useRef(false)
  const mounted = React.useRef(true)
  React.useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const isLoading = loading || actionPending
  const invalidSubmit = props.type === "submit" && form
    ? !form.formState.isValid || form.formState.isValidating
    : false
  const isDisabled = disabled || invalidSubmit
  const handleClick = (event) => {
    if (isDisabled || loading || actionPendingRef.current) {
      event.preventDefault()
      return
    }
    const result = onClick?.(event)
    if (result && typeof result.then === "function") {
      actionPendingRef.current = true
      setActionPending(true)
      result.then(
        () => { actionPendingRef.current = false; if (mounted.current) setActionPending(false) },
        () => { actionPendingRef.current = false; if (mounted.current) setActionPending(false) },
      )
    }
  }

  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      aria-busy={isLoading || undefined}
      aria-disabled={asChild && (isDisabled || isLoading) ? true : undefined}
      disabled={!asChild ? isDisabled || isLoading : undefined}
      onClick={handleClick}
      {...props}
    >
      {asChild ? children : <>
        <span className={cn("inline-flex items-center justify-center gap-2", isLoading && "invisible")}>{children}</span>
        {isLoading && <span className="absolute inset-0 inline-flex items-center justify-center gap-2 px-2" role="status">
          <SpinnerGap className="animate-spin" aria-hidden="true" />
          {size === "icon" ? <span className="sr-only">{loadingText || "Please wait"}</span> : <span>{loadingText || "Please wait"}</span>}
        </span>}
      </>}
    </Comp>
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
