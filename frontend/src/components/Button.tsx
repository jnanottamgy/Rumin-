import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";
import { cx } from "@/lib/cx";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface StyleProps {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  iconAfter?: ReactNode;
}

function classes(variant: Variant, size: Size, className?: string) {
  return cx(styles.button, styles[variant], styles[size], className);
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconAfter,
  className,
  children,
  type = "button",
  ...rest
}: StyleProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type={type} className={classes(variant, size, className)} {...rest}>
      {icon}
      {children && <span>{children}</span>}
      {iconAfter}
    </button>
  );
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  icon,
  iconAfter,
  className,
  children,
  ...rest
}: StyleProps & LinkProps) {
  return (
    <Link className={classes(variant, size, className)} {...rest}>
      {icon}
      <span>{children}</span>
      {iconAfter}
    </Link>
  );
}
