# new1

This file is assembled from every ticket's own lines (per-ticket entries here;
ticket 14 reconciles the whole tree against contracts 0.2 and 0.4).

## Tree

```
  constants/              where things are on this cluster: datasets, outputs, weights. Read by code;
                          nothing here changes a result or enters a key. Edited when something arrives or
                          moves on disk; a path may change only for the same bytes at a new place, and a
                          new set of weights is a new alias in models/table.yaml
    path_datasets.yaml      per environment: the clone's home, the interpreter that runs its loop, its data
                            root, and split name -> task-id file; plus the top-level venvs: map, which is
                            where every interpreter path in this repo is written down (Part 6.3)
      read by: data/environments/__init__.py (the splits block, to resolve a split name),
               data/environments/appworld.py (home, data root, split files),
               experimental_settings/schema.py (the splits block, to validate a split value at load),
               jobs/launch.py (the venv column and the venvs map), run.py (the venvs map, for selfcheck's
               per-interpreter import test)
    path_outputs.yaml       the outputs root on NFS, the debug subdirectory under it, the login_host and the
                            hosts: list, the cluster inventory (Part 6.3 holds the keys and their shape)
      read by: experimental_settings/schema.py (run_dir), jobs/registry.py (ls walks the root, and the
               hosts list for tmux and card probes), jobs/launch.py (the login_host and the hosts list),
               run.py (the login_host)
    path_models.yaml        weights alias -> the directory the weights live in
      read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)

  experimental_settings/  everything in here changes a result. The YAML files are gyb's: a new kind of
                          experiment is a new file, a new experiment is a new named setting in a file, a
                          tuning is an edited value. Agents read them and never edit them (a hook refuses).
                          schema.py is code and is edited for a new hyperparameter (with a default that
                          reproduces the old behavior) or a new value on an axis
    debug.yaml              only sizes, and Part 5.6 holds them; never a model and never a tuning;
                            --debug lays it over any setting
      read by: experimental_settings/schema.py only
    baseline.yaml           workflow sample, score; named settings inside
      read by: experimental_settings/schema.py only
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
      read by: experimental_settings/schema.py only
    inject.yaml             workflow inject, score; named settings inside
      read by: experimental_settings/schema.py only

  .claude/hooks/settings_readonly.sh       the hook that refuses any agent edit to
                          experimental_settings/*.yaml, and (Part 6.1) to models/table.yaml
```
