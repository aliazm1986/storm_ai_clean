# Data Folder

Raw data must not be committed to Git.

Recommended local layout:

data/
  raw/        local symlink or empty placeholder
  interim/    generated intermediate files, ignored by Git
  processed/  generated model-ready files, ignored by Git

Use an external DATA_ROOT path when running experiments.
