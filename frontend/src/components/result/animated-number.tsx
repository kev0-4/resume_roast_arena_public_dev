"use client";

import { useEffect, useState } from "react";
import { motion, useSpring } from "framer-motion";

// Adapted from a reference component (spring-driven count-up, triggered
// on scroll into view) -- reused here for the composite score, rank, and
// severity counts. Subscribes via useEffect with cleanup instead of
// calling spring.on(...) directly in the render body, which would
// re-subscribe a new listener on every render.
export function AnimatedNumber({
  value,
  className,
  suffix = "",
}: {
  value: number;
  className?: string;
  suffix?: string;
}) {
  const [display, setDisplay] = useState(0);
  const spring = useSpring(0, { bounce: 0, duration: 1000 });

  useEffect(() => {
    const unsubscribe = spring.on("change", (v) => setDisplay(Math.round(v)));
    return unsubscribe;
  }, [spring]);

  return (
    <motion.span
      className={className}
      onViewportEnter={() => spring.set(value)}
      viewport={{ once: true }}
    >
      {display}
      {suffix}
    </motion.span>
  );
}
