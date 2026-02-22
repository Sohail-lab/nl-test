import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "ui-btn ui-btn-size-default whitespace-nowrap text-sm [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "ui-btn-default",
        destructive: "ui-btn-destructive",
        outline: "ui-btn-outline",
        secondary: "ui-btn-secondary",
        ghost: "ui-btn-ghost",
        link: "ui-btn-link",
      },
      size: {
        default: "ui-btn-size-default",
        sm: "ui-btn-size-sm",
        lg: "ui-btn-size-lg",
        icon: "ui-btn-size-icon",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const Button = React.forwardRef(function Button(
  { className, variant, size, asChild = false, ...props },
  ref
) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  );
});

export { Button, buttonVariants };
