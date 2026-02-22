import React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef(({ className, type = "text", ...props }, ref) => {
  return (
    <input
      type={type}
      ref={ref}
      className={cn("ui-input", className)}
      {...props}
    />
  );
});

Input.displayName = "Input";

export { Input };
