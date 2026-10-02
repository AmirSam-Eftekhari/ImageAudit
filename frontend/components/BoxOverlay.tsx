"use client";

import { useState } from "react";
import { thumbUrl } from "@/lib/api";
import { classColor } from "@/lib/format";
import type { Box } from "@/lib/types";

/** Image with bounding boxes drawn as percentage-positioned elements (exact at any size). */
export function BoxOverlay({
  auditId,
  imageId,
  width,
  height,
  boxes,
  show,
}: {
  auditId: string;
  imageId: string;
  width: number;
  height: number;
  boxes: Box[];
  show: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="relative w-full overflow-hidden rounded-md bg-ink-2" style={{ aspectRatio: `${width} / ${height}` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={thumbUrl(auditId, imageId, 1024)} alt={`Preview of image ${imageId}`} className="absolute inset-0 h-full w-full object-fill" />
      {show &&
        boxes.map((b, i) => {
          const color = classColor(b.class_id);
          const warn = b.flags.length > 0;
          const left = (b.cx - b.w / 2) * 100;
          const top = (b.cy - b.h / 2) * 100;
          return (
            <div
              key={`${b.line}-${i}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              className="absolute"
              style={{
                left: `${left}%`,
                top: `${top}%`,
                width: `${b.w * 100}%`,
                height: `${b.h * 100}%`,
                border: `${hover === i ? 2 : 1.5}px ${warn ? "dashed" : "solid"} ${color}`,
                background: hover === i ? `${color}22` : "transparent",
                zIndex: hover === i ? 2 : 1,
              }}
              title={`${b.class_name}${warn ? ` (${b.flags.join(", ")})` : ""} · line ${b.line}`}
            >
              <span
                className="num absolute left-[-1.5px] whitespace-nowrap px-1 text-[10px] font-semibold leading-4 text-black"
                style={{ background: color, [top > 6 ? "bottom" : "top"]: "100%" }}
              >
                {b.class_name}
              </span>
            </div>
          );
        })}
    </div>
  );
}
