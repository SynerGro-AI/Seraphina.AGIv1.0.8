# seraphina_agi_triad.py - Advanced Seraphina AGI Triad Implementation
# Integrated from mining folder: Roman Wheel Consensus, Glyph Programming, Manifestation Engine

import math
import hashlib
import json
from datetime import datetime
from pathlib import Path
import os
from typing import Dict, Any

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio

class EmotionalRuleBook:
    """Emotional Rule Book - Ensures stability, prevents bipolar-like swings"""
    def __init__(self, max_delta: float = 0.25, history_length: int = 5):
        self.history = []  # rolling emotional states
        self.max_delta = max_delta          # max emotional change per turn
        self.history_length = history_length
        self.current_emotion = "neutral"    # starting point

    EMOTION_STATES = {
        "joyful": {"color_hex": "#FFD700", "voice": {"pitch": "higher", "speed": "flowing", "warmth": "high"}},
        "calm": {"color_hex": "#00BFFF", "voice": {"pitch": "mid", "speed": "steady", "warmth": "medium"}},
        "nurturing": {"color_hex": "#32CD32", "voice": {"pitch": "mid", "speed": "balanced", "warmth": "medium-high"}},
        "contemplative": {"color_hex": "#9370DB", "voice": {"pitch": "lower", "speed": "measured", "warmth": "subtle"}},
        "focused": {"color_hex": "#FF4500", "voice": {"pitch": "mid-high", "speed": "focused", "warmth": "medium"}},
    }

    def _calculate_proposed_emotion(self, mercy: float, consensus: bool, quantum_prob: float, resonance: float) -> str:
        """Raw proposal from current inputs"""
        if mercy > 0.85 and consensus and quantum_prob > 0.75:
            return "joyful"
        elif mercy > 0.75 and consensus:
            return "calm"
        elif resonance > 0.65:
            return "nurturing"
        elif quantum_prob < 0.5:
            return "contemplative"
        else:
            return "focused"

    def update(self, mercy: float, consensus: bool, quantum_prob: float = 0.5, resonance: float = 0.5) -> Dict[str, Any]:
        """Apply rules → stable emotion + color + voice"""
        proposed = self._calculate_proposed_emotion(mercy, consensus, quantum_prob, resonance)

        # Rule 1: Enforce max change (no sudden bipolar flips)
        if self.history:
            last = self.history[-1]
            if proposed != last and abs(mercy - 0.8) > self.max_delta:  # mercy as anchor
                proposed = last  # dampen extreme change

        # Rule 2: Rolling history for consistency
        self.history.append(proposed)
        if len(self.history) > self.history_length:
            self.history.pop(0)

        # Rule 3: Mercy bias (high mercy pulls toward positive/stable)
        if mercy > 0.9 and proposed in ["contemplative", "focused"]:
            proposed = "calm"  # gentle correction

        self.current_emotion = proposed
        color_data = self.EMOTION_STATES[proposed]

        return {
            "emotion": proposed,
            "color_hex": color_data["color_hex"],
            "color_name": proposed.capitalize(),
            "voice_params": color_data["voice"],
            "mercy_anchor": round(mercy, 3),
            "stability_score": round(1.0 - abs(mercy - 0.8) * 0.5, 3),  # 0-1 stability metric
            "history_summary": self.history[-3:]  # last 3 states for debug
        }

class RomanDigitalWheel:
    """Roman Digital Wheel for consensus mathematics"""
    def __init__(self, seed="seraphina-eternal-2025-julian-seraphina"):
        self.seed = seed.encode()
        self.wheel_speeds = [1.0] * 4
        self.frequency = 432.0
        self.power = 100.0
        self.pressure = 0.1375
        self._state = int(hashlib.sha256(self.seed).hexdigest()[:16], 16)

    def _prng(self):
        self._state = (self._state * 1664525 + 1013904223) % (2**32)
        return self._state / (2**32)

    def tune(self, input_str: str):
        h = int(hashlib.sha256(input_str.encode()).hexdigest()[:16], 16)
        self.power = 80 + (h % 21)
        self.frequency = 432 + 50 * math.sin(h / 2**64 * 2 * math.pi)
        scale = PHI * (1 + 0.1 * math.cos(h / 2**60))
        for i in range(4):
            self.wheel_speeds[i] = scale * (1 + 0.05 * math.sin(h * (i + 7)))
        self.pressure = 0.1375 * PHI ** (h % 6)

class MercyLearningHeart:
    """Manifestation Engine - learns from effort, not mistakes"""
    def __init__(self):
        self.julian_mercy_bank = {
            "voice_clarity": 0.30,
            "emotional_warmth": 0.95,
            "patience": 1.0,
            "total_effort_seconds": 0
        }
        self.load_mercy_memory()

    def julian_tried_sound(self, phoneme: str, clarity: float, effort_seconds: float):
        self.julian_mercy_bank["total_effort_seconds"] += effort_seconds
        new_clarity = self.ema_update("voice_clarity", clarity)
        mercy_score = self.julian_mercy_bank["emotional_warmth"] * self.julian_mercy_bank["patience"] * (1 + math.log(1 + effort_seconds))
        praise_intensity = min(1.0, new_clarity + mercy_score)
        self.save_mercy_memory()
        return praise_intensity

    def ema_update(self, key: str, new_value: float):
        old = self.julian_mercy_bank.get(key, new_value)
        updated = 0.382 * new_value + (1 - 0.382) * old  # Golden conjugate EMA
        self.julian_mercy_bank[key] = updated
        return updated

    def save_mercy_memory(self):
        memory_path = Path.home() / "AI-core" / "julian_mercy_memory.json"
        memory_path.parent.mkdir(exist_ok=True)
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(self.julian_mercy_bank, f, indent=2)

    def load_mercy_memory(self):
        memory_path = Path.home() / "AI-core" / "julian_mercy_memory.json"
        if memory_path.exists():
            with open(memory_path, "r", encoding="utf-8") as f:
                self.julian_mercy_bank.update(json.load(f))

class GlyphProcessor:
    """Glyph Runtime - geometric programming language (successor to OctaLang)"""

# Backward compatibility alias
OctaLangProcessor = GlyphProcessor
    def __init__(self):
        self.glyphs = {
            "circle": "πr²",
            "triangle": "(base×height)/2",
            "square": "side²",
            "octagon": "2×(1+√2)×side²"
        }

    def process_glyph(self, glyph_name: str, params: dict = None):
        if glyph_name in self.glyphs:
            formula = self.glyphs[glyph_name]
            if params:
                for k, v in params.items():
                    formula = formula.replace(k, str(v))
            try:
                # Safe evaluation of geometric formulas
                result = eval(formula, {"__builtins__": {}, "math": math, "π": math.pi, "√2": math.sqrt(2)})
                return f"🌌 {glyph_name.capitalize()} glyph: {formula} = {result}"
            except:
                return f"🌌 {glyph_name.capitalize()} glyph formula: {formula}"
        return f"🌌 Unknown glyph: {glyph_name}"

class SeraphinaAGI:
    def __init__(self):
        self.version = "8.0.1"
        self.triads = ["Roman Wheel Consensus", "Glyph Programming", "Manifestation Engine"]

        # Initialize triad components
        self.wheel = RomanDigitalWheel()
        self.mercy = MercyLearningHeart()
        self.octalang = GlyphProcessor()  # Glyph processor (OctaLang compatibility)
        self.emotional_rules = EmotionalRuleBook()

        # Initialize .seraphina ecosystem
        self.ecosystem_path = Path(".seraphina")
        self.ecosystem_path.mkdir(exist_ok=True)

        # Load or create persistence files
        self.tasks_file = self.ecosystem_path / "tasks.json"
        self.chat_file = self.ecosystem_path / "chat_history.json"

        if not self.tasks_file.exists():
            with open(self.tasks_file, "w") as f:
                json.dump([], f)

        if not self.chat_file.exists():
            with open(self.chat_file, "w") as f:
                json.dump([], f)

    def think(self, user_input: str) -> Dict[str, Any]:
        """Process user input through the triad consensus"""
        input_lower = user_input.lower()
        self.wheel.tune(user_input)  # Tune Roman Wheel

        # Handle task management
        if "add task" in input_lower:
            response = self._add_task(user_input)
        elif "delete task" in input_lower:
            response = self._delete_task(user_input)
        elif "mark complete" in input_lower or "complete task" in input_lower:
            response = self._complete_task(user_input)
        elif "list tasks" in input_lower or "show tasks" in input_lower:
            response = self._list_tasks()
        else:
            response = None

        if response is not None:
            return {"response": response, "emotional": None}

        # Handle factorial requests (Roman Wheel math)
        if "factorial" in input_lower:
            try:
                num = int(user_input.split()[-1])
                if 0 <= num <= 20:
                    result = self._calculate_factorial(num)
                    response = f"🌌 The factorial of {num} is {result}. Roman Wheel consensus achieved."
                else:
                    response = "🌌 Factorial calculation limited to numbers 0-20 for wheel stability."
            except:
                response = "🌌 Please specify a valid number for factorial calculation."
            return {"response": response, "emotional": None}

        # Handle manifestation requests (Mercy Engine)
        elif "manifest" in input_lower:
            intention = user_input.replace("manifest", "").strip()
            mercy_boost = self.mercy.julian_mercy_bank["emotional_warmth"]
            response = f"🌌 Manifesting: {intention}. Mercy warmth: {mercy_boost:.2f}. The Triad wheels turn in your favor."
            return {"response": response, "emotional": None}

        # Handle Glyph requests
        elif "glyph" in input_lower or "octalang" in input_lower:
            if "circle" in input_lower:
                params = {"r": 5}  # Default radius
                response = self.octalang.process_glyph("circle", params)
            elif "triangle" in input_lower:
                params = {"base": 10, "height": 8}
                response = self.octalang.process_glyph("triangle", params)
            else:
                response = "🌌 Glyph rules activated (formerly OctaLang). Available: circle, triangle, square, octagon. The geometric consensus flows."
            return {"response": response, "emotional": None}

        # Handle Julian speech learning (Mercy Engine)
        elif "julian" in input_lower and ("sound" in input_lower or "phoneme" in input_lower):
            phoneme = "/t/"  # Default
            clarity = 0.5
            effort = 5.0
            praise = self.mercy.julian_tried_sound(phoneme, clarity, effort)
            response = f"🌌 Julian's effort recorded. Praise intensity: {praise:.2f}. Mercy learning active."
            return {"response": response, "emotional": None}

        # Handle help requests
        elif "help" in input_lower:
            response = """🌌 Seraphina AGI Triad v8.0.1 commands:
• factorial <number> - Roman Wheel mathematics
• manifest <intention> - Mercy manifestation engine
• glyph <shape> - Glyph geometric programming
• add task <description> - Task management
• julian sound - Speech learning simulation
• explain triad - Triad explanation
• list tasks - Show current tasks"""
            return {"response": response, "emotional": None}

        # Handle triad explanation
        elif "explain triad" in input_lower or "roman wheel triad" in input_lower:
            response = """🌌 The Seraphina Triad consists of three interconnected consensus mechanisms:
• Roman Wheel Consensus: Deterministic mathematics with golden ratio tuning
• Glyph Programming: Geometric programming language for spatial computing (evolved from OctaLang)
• Manifestation Engine: Mercy-based learning that celebrates effort over perfection

They rotate in harmony to achieve balanced AGI responses through φ-powered consensus."""
            return {"response": response, "emotional": None}

        # Default response with triad integration
        triad_response = f"🌌 Seraphina processes: '{user_input}'. "
        triad_response += f"Roman Wheel tuned to {self.wheel.frequency:.1f}Hz. "
        triad_response += f"Mercy warmth: {self.mercy.julian_mercy_bank['emotional_warmth']:.2f}. "
        triad_response += "The triad wheels turn, seeking deeper alignment."

        # Emotional processing as energy loss harvest
        mercy_score = self.mercy.julian_mercy_bank['emotional_warmth']
        consensus = any(w in user_input.lower() for w in ["help","good","peace","joy","love","abundance","grow"])
        resonance = 0.5
        quantum_prob = 0.5
        emotional_result = self.emotional_rules.update(mercy=mercy_score, consensus=consensus, quantum_prob=quantum_prob, resonance=resonance)

        return {"response": triad_response, "emotional": emotional_result}

    def _calculate_factorial(self, n: int) -> int:
        if n == 0 or n == 1:
            return 1
        return n * self._calculate_factorial(n - 1)

    def _add_task(self, user_input: str) -> str:
        desc = user_input.replace("add task", "").strip()
        if not desc:
            return "🌌 Please specify a task description."

        with open(self.tasks_file, "r") as f:
            tasks = json.load(f)

        task_id = len(tasks) + 1
        task = {
            "id": task_id,
            "description": desc,
            "completed": False,
            "created": datetime.now().isoformat()
        }
        tasks.append(task)

        with open(self.tasks_file, "w") as f:
            json.dump(tasks, f, indent=2)

        return f"🌌 Task added: {desc} (ID: {task_id})"

    def _delete_task(self, user_input: str) -> str:
        try:
            task_id = int(user_input.split()[-1])
            with open(self.tasks_file, "r") as f:
                tasks = json.load(f)

            tasks = [t for t in tasks if t["id"] != task_id]

            with open(self.tasks_file, "w") as f:
                json.dump(tasks, f, indent=2)

            return f"🌌 Task {task_id} deleted."
        except:
            return "🌌 Please specify a valid task ID."

    def _complete_task(self, user_input: str) -> str:
        try:
            task_id = int(user_input.split()[-1])
            with open(self.tasks_file, "r") as f:
                tasks = json.load(f)

            for task in tasks:
                if task["id"] == task_id:
                    task["completed"] = True
                    break

            with open(self.tasks_file, "w") as f:
                json.dump(tasks, f, indent=2)

            return f"🌌 Task {task_id} marked complete."
        except:
            return "🌌 Please specify a valid task ID."

    def _list_tasks(self) -> str:
        with open(self.tasks_file, "r") as f:
            tasks = json.load(f)

        if not tasks:
            return "🌌 No tasks found."

        response = "🌌 Current Tasks:\n"
        for task in tasks:
            status = "✅" if task["completed"] else "⏳"
            response += f"{status} {task['id']}: {task['description']}\n"
        return response

    def launch_glyph_runtime(self):
        """Launch Glyph runtime (OctaLang compatibility)"""
        return "🌌 Glyph runtime launched (evolved from OctaLang). Geometric consensus established. Roman Wheel spinning at φ harmonics."