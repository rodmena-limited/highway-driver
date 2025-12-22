#!/usr/bin/env python3
"""Example: Running complex Python code on Highway via py=True.

This demonstrates the Driver's ability to execute arbitrary Python
functions remotely on Highway using tools.code.exec.

Usage:
    python examples/python_func.py
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def simulate_workday():
    """Simulates a developer's caffeine-fueled workday on Highway."""
    import random
    from dataclasses import dataclass

    @dataclass
    class CaffeineMolecule:
        potency: float
        half_life: int = 5
        is_organic: bool = True

    class BiologicalSystem:
        def __init__(self, name: str):
            self.name = name
            self.energy_level = 50.0
            self.jitter_factor = 0.0
            self.stomach_contents: list[CaffeineMolecule] = []
            self.tasks_completed = 0

        def ingest(self, item: CaffeineMolecule):
            print(f"[{self.name}] Ingesting caffeine... Neural pathways igniting.")
            self.stomach_contents.append(item)

        def process_metabolism(self):
            if not self.stomach_contents:
                self.energy_level -= 2.0
                return

            for mol in self.stomach_contents[:]:
                boost = mol.potency * (1 + (self.jitter_factor / 100))
                self.energy_level += boost
                self.jitter_factor += boost * 0.5
                mol.half_life -= 1
                if mol.half_life <= 0:
                    self.stomach_contents.remove(mol)

            self.energy_level = min(150.0, self.energy_level)
            self.jitter_factor = min(100.0, self.jitter_factor)

    class ProductivityEngine:
        def __init__(self, target_tasks: int):
            self.target_tasks = target_tasks
            self.logs = []

        def attempt_task(self, bio: BiologicalSystem) -> bool:
            if bio.energy_level < 20:
                self.logs.append("Too tired to move. Brain is a potato.")
                return False

            success_chance = (bio.energy_level / 100) - (bio.jitter_factor / 200)

            if random.random() < success_chance:
                bio.tasks_completed += 1
                self.logs.append(
                    f"Task {bio.tasks_completed} smashed! Speed: {bio.energy_level:.1f} OPS."
                )
                return True
            else:
                self.logs.append("Distracted by a shiny object or vibrating hands.")
                return False

    # Simulation parameters
    worker_name = "Senior Dev"
    espresso_shots = 4

    subject = BiologicalSystem(worker_name)
    engine = ProductivityEngine(target_tasks=10)

    # Pre-loading caffeine
    for _ in range(espresso_shots):
        subject.ingest(CaffeineMolecule(potency=random.uniform(10.0, 25.0)))

    print(f"\n--- Starting Workday for {worker_name} ---")

    for cycle in range(1, 11):
        subject.process_metabolism()
        success = engine.attempt_task(subject)

        status = "CRUSHING IT" if success else "IDLING"
        print(
            f"Cycle {cycle}: {status} | Energy: {subject.energy_level:.1f} | Jitters: {subject.jitter_factor:.1f}"
        )

        if subject.jitter_factor > 80:
            print("!! JITTER OVERLOAD !! Initiating emergency vibration sequence.")
            subject.jitter_factor *= 0.2
            subject.energy_level -= 30

    return {
        "subject": worker_name,
        "tasks_finished": subject.tasks_completed,
        "final_energy": round(subject.energy_level, 2),
        "final_jitter_score": round(subject.jitter_factor, 2),
        "outcome": "Promoted" if subject.tasks_completed > 7 else "Needs more beans",
        "logs": engine.logs,
    }


if __name__ == "__main__":
    print("Submitting caffeine simulation to Highway...")
    result = driver.run(wait=True, timeout=120)

    print(f"\nWorkflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.status == "completed":
        print("\n--- FINAL OFFICE REPORT ---")
        print("(Check Highway logs for detailed simulation output)")
