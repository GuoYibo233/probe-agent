"""Smoke test: can we init AlfredTWEnv, reset an episode, and step it?"""

import os

os.environ["ALFWORLD_DATA"] = "/home/y-guo/reproduce/new1/fig1_pilot/alfworld_data"

import yaml

import alfworld.agents.environment as environment

config = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "base_config.yaml")))

env = environment.get_environment("AlfredTWEnv")(config, train_eval="train")
env = env.init_env(batch_size=1)

obs, info = env.reset()
print("=== OBS ===")
print(obs[0][:600])
print("=== ADMISSIBLE (first 10) ===")
print(info["admissible_commands"][0][:10])

obs, scores, dones, infos = env.step(["look"])
print("=== AFTER look ===")
print(obs[0][:300])
print("scores:", scores, "dones:", dones)
print("SMOKE OK")
