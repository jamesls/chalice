import os
import platform


if platform.system() == 'Windows':
    def pip_script_in_venv(venv_dir):
        pip_exe = os.path.join(venv_dir, 'Scripts', 'pip.exe')
	return pip_exe

    def site_packages_dir_in_venv(venv_dir):
        deps_dir = os.path.join(venv_dir, 'Lib', 'site-packages')
	return deps_dir

else:
    # Posix platforms.

    def pip_script_in_venv(venv_dir):
        pip_exe = os.path.join(venv_dir, 'bin', 'pip')

    def site_packages_dir_in_venv(venv_dir):
        python_dir = os.listdir(os.path.join(venv_dir, 'lib'))[0]
        deps_dir = os.path.join(venv_dir, 'lib', python_dir, 'site-packages')
	return deps_dir
