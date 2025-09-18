# BOT_TOKEN = "8045284727:AAEndqxBJLhfcPlefAUuySDmwuLdxgn1ElU" # R145j7_TG-bot
BOT_TOKEN = "7913584298:AAGECC-CRqI2XqTC9hpNOXQ3Fcn2H4A8O3o" # DEV bot
TG_ID = 199310090

# Массив серверов с полным описанием
SERVERS = [
    {
        "name": "R145j7 VPN",
        "base_url": "http://127.0.0.1:58423",
        "token": "pk6lbA61zHmBK6%lJeE6ldUox6GLHo$6",
        "cpu_ram": {
            "cpu_high": 50,
            "cpu_low": 30,
            "ram_high": 85,
            "ram_low": 80,
            "interval": {
                "normal": 180,
                "warning": 60,
                "critical": 10
            }
        },
        "disk": {
            "threshold": 90,
            "interval": 3600
        },
        "processes_systemctl": {
            "interval": 300
        },
        "processes_pm2": {
            "interval": 300
        },
        "updates": {
            "time": "07:00"
        }
    },
    {
        "name": "UDH SERVER",
        "base_url": "http://83.229.84.192:58423",
        "token": "aZ7@Lp9Vd6qW2!mN4r$X8hJzC1e%KtY",
        "cpu_ram": {
            "cpu_high": 50,
            "cpu_low": 30,
            "ram_high": 90,
            "ram_low": 80,
            "interval": {
                "normal": 180,
                "warning": 60,
                "critical": 10
            }
        },
        "disk": {
            "threshold": 90,
            "interval": 3600
        },
        "processes_systemctl": {
            "interval": 300
        },
        "processes_pm2": {
            "interval": 300
        },
        "updates": {
            "time": "07:00"
        }
    },
    {
        "name": "KOVAL VDS",
        "base_url": "http://157.90.105.110:58423",
        "token": "Bw8!Ns4vKq!L2@tX7r$M9dFyZ3h%GpVc",
        "cpu_ram": {
            "cpu_high": 50,
            "cpu_low": 30,
            "ram_high": 90,
            "ram_low": 80,
            "interval": {
                "normal": 180,
                "warning": 60,
                "critical": 10
            }
        },
        "disk": {
            "threshold": 90,
            "interval": 3600
        },
        "processes_systemctl": {
            "interval": 300
        },
        "processes_pm2": {
            "interval": 300
        },
        "updates": {
            "time": "07:00"
        }
    },
    {
        "name": "AP SERVER",
        "base_url": "http://185.139.230.208:58423",
        "token": "G7rLp2Vz6qMn9Y4XtHwJc3eBkT8",
        "cpu_ram": {
            "cpu_high": 50,
            "cpu_low": 30,
            "ram_high": 80,
            "ram_low": 70,
            "interval": {
                "normal": 180,
                "warning": 60,
                "critical": 10
            }
        },
        "disk": {
            "threshold": 90,
            "interval": 3600
        },
        "processes_systemctl": {
            "interval": 300
        },
        "processes_pm2": {
            "interval": 300
        },
        "updates": {
            "time": "07:00"
        }
    }
]

SITES_MONITOR = {
    "interval": 3600,
    "urls": [
        "https://impact-ac-wr.pl",
        "https://aquaprylad.in.ua",
        "https://crm.aquaprylad.in.ua",
        "https://смартметрика.укр"
    ]
}

MINER_SCAN = {
    "interval": 3600,
    "processes": [
        "xmrig", "minerd", "cpuminer", "cgminer", "ethminer", "bfgminer",
        "mining", "cryptonight", "monero", "xmr-stak", "teamredminer",
        "nbminer", "phoenixminer", "lolminer", "trex", "gminer", "nicehash"
    ]
}