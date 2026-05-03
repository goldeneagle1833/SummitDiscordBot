import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import ReportGameModal from "@/components/player/ReportGameModal";
import usePageTitle from "@/hooks/usePageTitle";

const STARTING_LIFE = 20;

const ELEMENT_IMG = "/static/images/elements/";
const ELEMENTS = [
  { key: "earth", label: "Earth", file: "earth.png" },
  { key: "fire", label: "Fire", file: "fire.png" },
  { key: "air", label: "Air", file: "wind.png" },
  { key: "water", label: "Water", file: "water.png" },
];

const DICE = [
  {
    sides: 20,
    label: "d20",
    // Hexagon
    path: "M12 2L3.27 6.5v11L12 22l8.73-4.5v-11L12 2z",
  },
  {
    sides: 12,
    label: "d12",
    // Pentagon
    path: "M12 2L2.24 9.5 5.97 21h12.06l3.73-11.5L12 2z",
  },
  {
    sides: 8,
    label: "d8",
    // Diamond
    path: "M12 2L2 12l10 10 10-10L12 2z",
  },
  {
    sides: 6,
    label: "d6",
    // Square
    path: "M4 4h16v16H4z",
  },
  {
    sides: 4,
    label: "d4",
    // Triangle
    path: "M12 3L2 21h20L12 3z",
    textY: 16,
  },
];

function DiceIcon({ dice, size = 24 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5">
      <path d={dice.path} />
      <text
        x="12"
        y={dice.textY || 14}
        textAnchor="middle"
        fontSize="6"
        fill="currentColor"
        stroke="none"
        fontWeight="bold">
        {dice.sides}
      </text>
    </svg>
  );
}

function ThresholdCounter({ element, count, onChange }) {
  const holdTimer = useRef(null);
  const holdInterval = useRef(null);
  const countRef = useRef(count);
  countRef.current = count;

  const startHold = (delta) => {
    onChange(Math.max(0, count + delta));
    holdTimer.current = setTimeout(() => {
      holdInterval.current = setInterval(() => {
        const next = Math.max(0, countRef.current + (delta > 0 ? 5 : -5));
        onChange(next);
      }, 300);
    }, 2000);
  };

  const stopHold = () => {
    clearTimeout(holdTimer.current);
    clearInterval(holdInterval.current);
  };

  useEffect(() => {
    return () => {
      clearTimeout(holdTimer.current);
      clearInterval(holdInterval.current);
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col select-none touch-manipulation relative">
      {/* Top half: + tap zone */}
      <button
        className="flex-1 bg-bg-surface/50 border border-border/30 active:bg-white/10 transition-colors"
        onPointerDown={(e) => { e.stopPropagation(); startHold(1); }}
        onPointerUp={stopHold}
        onPointerLeave={stopHold}
        onPointerCancel={stopHold}
        onContextMenu={(e) => e.preventDefault()}
      />
      {/* Center: icon + count side by side (overlaid on the split) */}
      <div className="absolute inset-0 flex items-center justify-center gap-1 pointer-events-none">
        <span className="text-white text-2xl font-bold drop-shadow-md leading-none">
          {count}
        </span>
        <img
          src={`${ELEMENT_IMG}${element.file}`}
          alt={element.label}
          className="w-6 h-6 object-contain opacity-85"
        />
      </div>
      {/* Bottom half: - tap zone */}
      <button
        className="flex-1 bg-bg-surface/50 border border-border/30 active:bg-white/10 transition-colors"
        onPointerDown={(e) => { e.stopPropagation(); startHold(-1); }}
        onPointerUp={stopHold}
        onPointerLeave={stopHold}
        onPointerCancel={stopHold}
        onContextMenu={(e) => e.preventDefault()}
      />
    </div>
  );
}

function ThresholdRow({ thresholds, onChange }) {
  return (
    <div className="flex w-full">
      {ELEMENTS.map((el) => (
        <ThresholdCounter
          key={el.key}
          element={el}
          count={thresholds[el.key]}
          onChange={(val) => onChange({ ...thresholds, [el.key]: val })}
        />
      ))}
    </div>
  );
}

function PlayerHalf({
  life,
  onLifeChange,
  thresholds,
  onThresholdChange,
  flipped,
  playerNum,
  isDead,
}) {
  const holdTimer = useRef(null);
  const holdInterval = useRef(null);

  const clamp = (v) => Math.max(0, Math.min(STARTING_LIFE, v));

  const startHold = useCallback(
    (delta) => {
      onLifeChange((v) => clamp(v + delta));
      holdTimer.current = setTimeout(() => {
        holdInterval.current = setInterval(() => {
          onLifeChange((v) => clamp(v + delta));
        }, 120);
      }, 400);
    },
    [onLifeChange],
  );

  const stopHold = useCallback(() => {
    clearTimeout(holdTimer.current);
    clearInterval(holdInterval.current);
  }, []);

  useEffect(() => {
    return () => {
      clearTimeout(holdTimer.current);
      clearInterval(holdInterval.current);
    };
  }, []);

  return (
    <div
      className="flex-1 flex flex-col relative select-none"
      style={{ transform: flipped ? "rotate(180deg)" : undefined }}>
      {/* Threshold counters at the edge */}
      <ThresholdRow thresholds={thresholds} onChange={onThresholdChange} />

      {/* Life total area */}
      <div className="flex-1 flex flex-col items-center justify-center relative">
        {/* Tap zone: top half = increment */}
        <button
          className="absolute inset-x-0 top-0 h-1/2 z-10 touch-manipulation active:bg-white/5 transition-colors"
          onPointerDown={() => startHold(1)}
          onPointerUp={stopHold}
          onPointerLeave={stopHold}
          onPointerCancel={stopHold}
          aria-label="Increase life"
        />
        {/* Tap zone: bottom half = decrement */}
        <button
          className="absolute inset-x-0 bottom-0 h-1/2 z-10 touch-manipulation active:bg-white/5 transition-colors"
          onPointerDown={() => startHold(-1)}
          onPointerUp={stopHold}
          onPointerLeave={stopHold}
          onPointerCancel={stopHold}
          aria-label="Decrease life"
        />

        {/* Small +/- indicators */}
        <span className="text-text-muted/30 text-2xl font-bold pointer-events-none">
          +
        </span>

        {/* Life number */}
        <span
          className={`font-display leading-none pointer-events-none transition-colors ${
            isDead ? "text-accent-red" : "text-white"
          }`}
          style={{ fontSize: "clamp(9rem, 38vw, 20rem)" }}>
          {life}
        </span>

        <span className="text-text-muted/30 text-2xl font-bold pointer-events-none">
          &minus;
        </span>
      </div>
    </div>
  );
}

function DiceRollerStrip({ onReset }) {
  const [rollResult, setRollResult] = useState(null);
  const [rolling, setRolling] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(!!document.fullscreenElement);
  const rollTimeout = useRef(null);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  };

  const rollDice = (sides) => {
    setRolling(true);
    clearTimeout(rollTimeout.current);

    let count = 0;
    const anim = setInterval(() => {
      setRollResult({ sides, value: Math.floor(Math.random() * sides) + 1 });
      count++;
      if (count > 8) {
        clearInterval(anim);
        const final = Math.floor(Math.random() * sides) + 1;
        setRollResult({ sides, value: final });
        setRolling(false);
        rollTimeout.current = setTimeout(() => setRollResult(null), 4000);
      }
    }, 60);
  };

  const clearRoll = () => {
    clearTimeout(rollTimeout.current);
    setRollResult(null);
    setRolling(false);
  };

  useEffect(() => {
    return () => clearTimeout(rollTimeout.current);
  }, []);

  return (
    <div className="flex items-center justify-center gap-1 py-2 bg-bg-surface/80 border-y border-border/50 relative z-20">
      {/* Clear dice roll */}
      <button
        onClick={clearRoll}
        className="p-2 text-text-muted hover:text-white transition-colors touch-manipulation"
        title="Clear roll"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      {/* Dice buttons */}
      {DICE.map((d) => (
        <button
          key={d.sides}
          onClick={() => rollDice(d.sides)}
          className="p-2 text-text-muted hover:text-white active:scale-110 transition-all touch-manipulation"
          title={`Roll ${d.label}`}>
          <DiceIcon dice={d} size={28} />
        </button>
      ))}

      {/* Reset button */}
      <button
        onClick={onReset}
        className="p-2 text-text-muted hover:text-white active:scale-110 transition-all touch-manipulation"
        title="Reset">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2">
          <path d="M3 12a9 9 0 1 1 3 6.7" />
          <path d="M3 22v-6h6" />
        </svg>
      </button>

      {/* Fullscreen button */}
      <button
        onClick={toggleFullscreen}
        className="p-2 text-text-muted hover:text-white active:scale-110 transition-all touch-manipulation"
        title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          {isFullscreen ? (
            <>
              <path d="M4 14h6v6" /><path d="M14 10h6V4" />
              <path d="M20 4l-6 6" /><path d="M4 20l6-6" />
            </>
          ) : (
            <>
              <path d="M8 3H5a2 2 0 00-2 2v3" />
              <path d="M21 8V5a2 2 0 00-2-2h-3" />
              <path d="M3 16v3a2 2 0 002 2h3" />
              <path d="M16 21h3a2 2 0 002-2v-3" />
            </>
          )}
        </svg>
      </button>

      {/* Roll result overlay */}
      {rollResult && (
        <div
          className={`absolute inset-0 flex items-center justify-center bg-bg-dark/90 z-30 pointer-events-none ${rolling ? "animate-pulse" : ""}`}>
          <span className="text-3xl font-display text-secondary">
            {rollResult.value}
          </span>
          <span className="text-sm text-text-muted ml-2">
            ({DICE.find((d) => d.sides === rollResult.sides)?.label})
          </span>
        </div>
      )}
    </div>
  );
}


const defaultThresholds = () => ({ earth: 0, fire: 0, air: 0, water: 0 });

export default function LifeCounter() {
  usePageTitle("Life Counter");
  const { user } = useAuth();
  const [p1Life, setP1Life] = useState(STARTING_LIFE);
  const [p2Life, setP2Life] = useState(STARTING_LIFE);
  const [p1Thresholds, setP1Thresholds] = useState(defaultThresholds);
  const [p2Thresholds, setP2Thresholds] = useState(defaultThresholds);
  const [showReport, setShowReport] = useState(false);

  const reset = () => {
    setP1Life(STARTING_LIFE);
    setP2Life(STARTING_LIFE);
    setP1Thresholds(defaultThresholds());
    setP2Thresholds(defaultThresholds());
  };

  const someoneDead = p1Life <= 0 || p2Life <= 0;
  const canReport = someoneDead && user;

  return (
    <>
      {/* Full-viewport container — escapes the normal page layout padding */}
      <div
        className="fixed inset-0 z-40 flex flex-col bg-bg-dark"
        style={{ touchAction: "manipulation" }}>
        {/* Player 2 (top, rotated 180) */}
        <PlayerHalf
          life={p2Life}
          onLifeChange={setP2Life}
          thresholds={p2Thresholds}
          onThresholdChange={setP2Thresholds}
          flipped={true}
          playerNum={2}
          isDead={p2Life <= 0}
        />

        {/* Center dice strip */}
        <DiceRollerStrip onReset={reset} />

        {/* Player 1 (bottom, normal) */}
        <PlayerHalf
          life={p1Life}
          onLifeChange={setP1Life}
          thresholds={p1Thresholds}
          onThresholdChange={setP1Thresholds}
          flipped={false}
          playerNum={1}
          isDead={p1Life <= 0}
        />

        {/* Report button — slides in when someone hits 0 */}
        {someoneDead && (
          <div className="absolute bottom-4 left-0 right-0 flex justify-center z-50 animate-fade-in">
            {canReport ? (
              <button
                onClick={() => setShowReport(true)}
                className="px-6 py-3 bg-secondary text-black font-semibold rounded-soft shadow-harsh text-sm hover:opacity-90 transition-opacity">
                Report Game
              </button>
            ) : (
              <div className="px-4 py-2 bg-bg-surface/90 border border-border rounded-soft text-xs text-text-muted">
                Log in to report this game
              </div>
            )}
          </div>
        )}
      </div>

      {/* Report modal */}
      {showReport && user && (
        <ReportGameModal
          playerId={user.user_id}
          onClose={() => setShowReport(false)}
          onReported={() => setShowReport(false)}
          initialLifeSubmitter={p1Life}
          initialLifeOpponent={p2Life}
        />
      )}
    </>
  );
}
