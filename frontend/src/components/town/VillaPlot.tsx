import type { VillaItem } from "@/api/town";
import {
  CODE_COLOR, KIND_COLOR, TH, TW, blockHeight, corner, drawOrder, footprint, plotArt, rhombus, spriteOf, viewBox,
} from "@/lib/villa";

type Ghost = { x: number; y: number; w: number; h: number; ok: boolean };

/** The isometric plot of «Моя вилла»: the lawn, its cells and the things
 * standing on it (pictures, or coloured blocks until a picture exists).
 * Read-only unless onCell / onItem are given (the owner's editor). */
export default function VillaPlot({
  grid, items, selectedId, ghost, onCell, onItem, label,
}: {
  grid: number;
  items: VillaItem[];
  selectedId?: number | null;
  /** Where the selected thing would land, green / red. */
  ghost?: Ghost | null;
  onCell?: (x: number, y: number) => void;
  onItem?: (item: VillaItem) => void;
  label: string;
}) {
  const { width, height } = viewBox(grid);
  const ground = plotArt();
  const editing = Boolean(onCell);
  const [top, right, bottom, left] = [corner(grid, 0, 0), corner(grid, grid, 0), corner(grid, grid, grid), corner(grid, 0, grid)];
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="block h-auto w-full select-none"
      role="img"
      aria-label={label}
      data-testid="villa-plot"
    >
      <defs>
        <linearGradient id="villa-lawn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9be07f" />
          <stop offset="1" stopColor="#5fb85a" />
        </linearGradient>
      </defs>
      {ground ? (
        <image href={ground} x={0} y={0} width={width} height={height} preserveAspectRatio="xMidYMid slice" />
      ) : (
        <>
          {/* the plot's edge: a low stone wall under the lawn */}
          <polygon
            points={`${left[0]},${left[1]} ${bottom[0]},${bottom[1]} ${right[0]},${right[1]} ${right[0]},${right[1] + 10} ${bottom[0]},${bottom[1] + 10} ${left[0]},${left[1] + 10}`}
            fill="#c9b48f"
          />
          <polygon points={`${top[0]},${top[1]} ${right[0]},${right[1]} ${bottom[0]},${bottom[1]} ${left[0]},${left[1]}`} fill="url(#villa-lawn)" />
        </>
      )}
      {editing && Array.from({ length: grid * grid }, (_, i) => {
        const x = i % grid;
        const y = Math.floor(i / grid);
        return (
          <polygon
            key={i}
            points={rhombus(grid, x, y, 1, 1)}
            fill="transparent"
            stroke="rgba(255,255,255,0.28)"
            strokeWidth={1}
            onClick={() => onCell?.(x, y)}
            data-testid={`villa-cell-${x}-${y}`}
          />
        );
      })}
      {ghost && (
        <polygon
          points={rhombus(grid, ghost.x, ghost.y, ghost.w, ghost.h)}
          fill={ghost.ok ? "rgba(132,255,120,0.35)" : "rgba(255,80,80,0.4)"}
          stroke={ghost.ok ? "#84ff78" : "#ff5050"}
          strokeWidth={2}
          pointerEvents="none"
        />
      )}
      {drawOrder(items).map((item) => (
        <Thing
          key={item.id}
          grid={grid}
          item={item}
          selected={item.id === selectedId}
          onTap={onItem ? () => onItem(item) : undefined}
        />
      ))}
    </svg>
  );
}

function Thing({ grid, item, selected, onTap }: { grid: number; item: VillaItem; selected: boolean; onTap?: () => void }) {
  const [w, h] = footprint(item);
  const x = item.x ?? 0;
  const y = item.y ?? 0;
  const sprite = spriteOf(item);
  const front = corner(grid, x + w, y + h);
  const leftC = corner(grid, x, y + h);
  const rightC = corner(grid, x + w, y);
  const centerX = (leftC[0] + rightC[0]) / 2;
  const spriteW = (w + h) * (TW / 2);
  const outline = selected ? (
    <polygon points={rhombus(grid, x, y, w, h)} fill="rgba(255,226,92,0.25)" stroke="#ffe25c" strokeWidth={3} />
  ) : null;
  const common = {
    onClick: onTap,
    style: { cursor: onTap ? "pointer" : undefined },
    "data-testid": `villa-item-${item.code}`,
  };
  if (sprite) {
    const spriteH = spriteW * 1.25;
    return (
      <g {...common}>
        {outline}
        <image
          href={sprite}
          x={centerX - spriteW / 2}
          y={front[1] + TH * 0.15 - spriteH}
          width={spriteW}
          height={spriteH}
          preserveAspectRatio="xMidYMax meet"
          transform={item.rot ? `translate(${centerX * 2},0) scale(-1,1)` : undefined}
        />
      </g>
    );
  }
  const lift = blockHeight(item);
  const [topC, sideL, sideR] = KIND_COLOR[item.kind];
  const fill = CODE_COLOR[item.code] ?? topC;
  const backC = corner(grid, x, y);
  const emojiSize = Math.min(30, 12 + (w + h) * 4);
  return (
    <g {...common}>
      {outline}
      <polygon points={`${leftC[0]},${leftC[1]} ${front[0]},${front[1]} ${front[0]},${front[1] - lift} ${leftC[0]},${leftC[1] - lift}`} fill={sideL} />
      <polygon points={`${front[0]},${front[1]} ${rightC[0]},${rightC[1]} ${rightC[0]},${rightC[1] - lift} ${front[0]},${front[1] - lift}`} fill={sideR} />
      <polygon points={rhombus(grid, x, y, w, h, lift)} fill={fill} stroke="rgba(0,0,0,0.12)" />
      <text
        x={centerX}
        y={(backC[1] + front[1]) / 2 - lift + emojiSize * 0.35}
        textAnchor="middle"
        fontSize={emojiSize}
      >
        {item.emoji}
      </text>
      {item.level != null && item.code === "villa" && (
        <text x={centerX} y={front[1] - lift * 0.35} textAnchor="middle" fontSize={11} fontWeight={700} fill="#5b4a2e">
          {"★".repeat(item.level)}
        </text>
      )}
    </g>
  );
}
