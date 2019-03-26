from setuptools import setup, find_packages

version = {}
with open("spine_dbapi/version.py") as fp:
    exec(fp.read(), version)

setup(
    name='spine_dbapi',
    version=version['__version__'],
    description='An API to talk to Spine databases',
    url='https://github.com/Spine-project/Spine-Database-API',
    author='Manuel Marin, Per Vennström, Fabiano Pallonetto',
    author_email='manuelma@kth.se',
    license='LGPL',
    packages=find_packages(),
    install_requires=[
          'sqlalchemy',
          'alembic',
          'faker'
      ],
    include_package_data=True,
    zip_safe=False
)
