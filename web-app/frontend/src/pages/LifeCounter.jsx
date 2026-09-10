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
    sides: 6,
    label: "d6",
    // Square
    path: "M4 4h16v16H4z",
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
    <div className="grid grid-cols-4 w-full" style={{ height: "calc(25vw * 0.75)" }}>
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

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function TimerHalf({ seconds, isActive, canStart, onPassTurn, flipped }) {
  const enabled = isActive || canStart;
  return (
    <div
      className="flex-1 flex flex-col relative select-none"
      style={{ transform: flipped ? "rotate(180deg)" : undefined }}>
      <div className="flex-1 flex flex-col items-center justify-center">
        {/* Pass Turn / Start button */}
        <button
          onClick={onPassTurn}
          disabled={!enabled}
          className={`px-8 py-3 rounded-soft font-semibold text-sm transition-all touch-manipulation ${
            enabled
              ? "bg-secondary text-black hover:opacity-90 active:scale-95"
              : "bg-bg-surface/50 text-text-muted/40 cursor-not-allowed"
          }`}>
          {canStart ? "Start" : "Pass Turn"}
        </button>

        {/* Timer display */}
        <span
          className={`font-display leading-none pointer-events-none transition-colors ${
            isActive ? "text-secondary" : "text-text-muted/50"
          }`}
          style={{ fontSize: "clamp(6rem, 28vw, 14rem)" }}>
          {formatTime(seconds)}
        </span>

        {/* Active indicator */}
        <span className={`text-sm font-semibold ${isActive ? "text-secondary" : "text-text-muted/30"}`}>
          {isActive ? "Your turn" : canStart ? "Tap Start" : "Waiting"}
        </span>
      </div>
    </div>
  );
}

function DiceRollerStrip({ onReset, wakeLock, onToggleWakeLock, timerMode, onToggleTimer }) {
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

      {/* Wake lock (keep screen on) */}
      {"wakeLock" in navigator && (
        <button
          onClick={onToggleWakeLock}
          className={`p-2 active:scale-110 transition-all touch-manipulation ${wakeLock ? "text-secondary" : "text-text-muted hover:text-white"}`}
          title={wakeLock ? "Allow screen sleep" : "Keep screen on"}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill={wakeLock ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        </button>
      )}

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

      {/* Timer mode toggle */}
      <button
        onClick={onToggleTimer}
        className={`p-2 active:scale-110 transition-all touch-manipulation ${timerMode ? "text-secondary" : "text-text-muted hover:text-white"}`}
        title={timerMode ? "Switch to life counter" : "Switch to turn timer"}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="13" r="8" />
          <path d="M12 9v4l2 2" />
          <path d="M9 1h6" />
          <path d="M12 1v2" />
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
  const [wakeLock, setWakeLock] = useState(null);
  const wakeLockRef = useRef(null);

  // Timer mode state
  const [timerMode, setTimerMode] = useState(false);
  const [activePlayer, setActivePlayer] = useState(null); // 1 or 2 or null
  const [p1Time, setP1Time] = useState(0);
  const [p2Time, setP2Time] = useState(0);
  const timerRef = useRef(null);

  const toggleWakeLock = async () => {
    if (wakeLockRef.current) {
      await wakeLockRef.current.release();
      wakeLockRef.current = null;
      setWakeLock(null);
    } else {
      try {
        wakeLockRef.current = await navigator.wakeLock.request("screen");
        setWakeLock(true);
        wakeLockRef.current.addEventListener("release", () => {
          wakeLockRef.current = null;
          setWakeLock(null);
        });
      } catch {
        // Wake lock request failed (e.g. low battery)
      }
    }
  };

  // Re-acquire wake lock when page becomes visible again (browser releases it on tab switch)
  useEffect(() => {
    const onVisibility = async () => {
      if (document.visibilityState === "visible" && wakeLock && !wakeLockRef.current) {
        try {
          wakeLockRef.current = await navigator.wakeLock.request("screen");
          wakeLockRef.current.addEventListener("release", () => {
            wakeLockRef.current = null;
            setWakeLock(null);
          });
        } catch {
          // Failed to re-acquire
        }
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [wakeLock]);

  // Release wake lock on unmount
  useEffect(() => {
    return () => {
      if (wakeLockRef.current) {
        wakeLockRef.current.release();
      }
    };
  }, []);

  // Timer tick
  useEffect(() => {
    if (activePlayer) {
      timerRef.current = setInterval(() => {
        if (activePlayer === 1) setP1Time((t) => t + 1);
        else setP2Time((t) => t + 1);
      }, 1000);
    }
    return () => clearInterval(timerRef.current);
  }, [activePlayer]);

  const toggleTimerMode = () => {
    setTimerMode((v) => !v);
    setActivePlayer(null);
    setP1Time(0);
    setP2Time(0);
  };

  const passTurn = (fromPlayer) => {
    if (fromPlayer === 1) setP1Time(0);
    else setP2Time(0);
    setActivePlayer(fromPlayer === 1 ? 2 : 1);
  };

  const reset = () => {
    setP1Life(STARTING_LIFE);
    setP2Life(STARTING_LIFE);
    setP1Thresholds(defaultThresholds());
    setP2Thresholds(defaultThresholds());
    setActivePlayer(null);
    setP1Time(0);
    setP2Time(0);
  };

  const someoneDead = p1Life <= 0 || p2Life <= 0;
  const canReport = someoneDead && user;

  return (
    <>
      {/* Full-viewport container — escapes the normal page layout padding */}
      <div
        className="fixed inset-x-0 top-16 bottom-0 z-40 flex flex-col bg-bg-dark"
        style={{ touchAction: "manipulation" }}>
        {/* Player 2 (top, rotated 180) */}
        {timerMode ? (
          <TimerHalf
            seconds={p2Time}
            isActive={activePlayer === 2}
            canStart={activePlayer === null}
            onPassTurn={() => passTurn(2)}
            flipped={true}
          />
        ) : (
          <PlayerHalf
            life={p2Life}
            onLifeChange={setP2Life}
            flipped={true}
            playerNum={2}
            isDead={p2Life <= 0}
          />
        )}

        {/* Center: P2 thresholds, dice strip, P1 thresholds */}
        {!timerMode && (
        <div className="relative z-20" style={{ transform: "rotate(180deg)" }}>
          <ThresholdRow thresholds={p2Thresholds} onChange={setP2Thresholds} />
        </div>
        )}
        <DiceRollerStrip onReset={reset} wakeLock={wakeLock} onToggleWakeLock={toggleWakeLock} timerMode={timerMode} onToggleTimer={toggleTimerMode} />
        {!timerMode && (
        <div className="relative z-20">
          <ThresholdRow thresholds={p1Thresholds} onChange={setP1Thresholds} />
        </div>
        )}

        {/* Player 1 (bottom, normal) */}
        {timerMode ? (
          <TimerHalf
            seconds={p1Time}
            isActive={activePlayer === 1}
            canStart={activePlayer === null}
            onPassTurn={() => passTurn(1)}
            flipped={false}
          />
        ) : (
          <PlayerHalf
            life={p1Life}
            onLifeChange={setP1Life}
            flipped={false}
            playerNum={1}
            isDead={p1Life <= 0}
          />
        )}

        {/* Report button — slides in when someone hits 0 */}
        {!timerMode && someoneDead && (
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
