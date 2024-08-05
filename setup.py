from setuptools import setup, find_packages

setup(
    name="devops-python-scripts",
    version="1.3.0",
    author="Vikas Dhamija",
    description="DevOps automation scripts — EKS health check, Vault rotation, incident triage",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.9",
    install_requires=[
        "kubernetes>=28.1.0",
        "hvac>=2.1.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "eks-health-check=eks_health_check.main:main",
            "vault-rotation=vault_rotation.main:main",
            "incident-triage=incident_triage.main:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
