import { useCallback, useRef } from "react";

interface Props {
  onResize: (deltaX: number) => void;
}

export function Resizer({ onResize }: Props) {
  const lastX = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      lastX.current = e.clientX;
      const body = document.body;
      const prevCursor = body.style.cursor;
      body.style.cursor = "col-resize";
      const move = (ev: MouseEvent) => {
        const dx = ev.clientX - lastX.current;
        lastX.current = ev.clientX;
        onResize(dx);
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        body.style.cursor = prevCursor;
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    },
    [onResize]
  );

  return (
    <div
      onMouseDown={onMouseDown}
      className="absolute top-0 right-0 h-full w-1 cursor-col-resize hover:bg-accent/40 transition-colors"
      style={{ translate: "50% 0" }}
    />
  );
}
