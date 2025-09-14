BOT_TOKEN = "8045284727:AAEndqxBJLhfcPlefAUuySDmwuLdxgn1ElU" # R145j7_TG-bot
# BOT_TOKEN = "7913584298:AAGECC-CRqI2XqTC9hpNOXQ3Fcn2H4A8O3o" # DEV bot
TG_ID = 199310090

# Массив серверов с полным описанием
SERVERS = [
    {
        "name": "R145j7 VPN",
        "type": "local",
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
        "processes": {
            "enabled": True,
            "required": ["mysql"],
            "interval": 300
        },
        "updates": {
            "enabled": True,
            "time": "07:00"
        }
    },
    {
        "name": "UDH SERVER",
        "type": "remote",
        "base_url": "http://83.229.84.192:58423",
        "token": "aZ7@Lp9Vd6qW2!mN4r$X8hJzC1e%KtY",
        "cpu_ram": {
            "url": "/cpu_ram",
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
            "url": "/disk",
            "threshold": 90,
            "interval": 3600
        },
        "processes": {
            "url": "/processes",
            "required": ["fail2ban", "global-bot", "global-hook-listener", "mysql", "nginx", "server_monitoring", "telegram-bot", "webhook-handler"],
            "interval": 300
        },
        "updates": {
            "url": "/updates",
            "time": "07:00"
        }
    },
    {
        "name": "KOVAL VDS",
        "type": "remote",
        "base_url": "http://157.90.105.110:58423",
        "token": "Bw8!Ns4vKq!L2@tX7r$M9dFyZ3h%GpVc",
        "cpu_ram": {
            "url": "/cpu_ram",
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
            "url": "/disk",
            "threshold": 90,
            "interval": 3600
        },
        "processes": {
            "url": "/processes",
            "required": ["mariadb", "apache2", "fail2ban", "nginx", "server_monitoring"],
            "interval": 300
        },
        "updates": {
            "url": "/updates",
            "time": "07:00"
        }
    },
    {
        "name": "AP SERVER",
        "type": "remote",
        "base_url": "http://185.139.230.208:58423",
        "token": "G7rLp2Vz6qMn9Y4XtHwJc3eBkT8",
        "cpu_ram": {
            "url": "/cpu_ram",
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
            "url": "/disk",
            "threshold": 90,
            "interval": 3600
        },
        "processes": {
            "url": "/processes",
            "required": ["fail2ban", "mysql", "nginx", "server_monitoring"],
            "interval": 300
        },
        "updates": {
            "url": "/updates",
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