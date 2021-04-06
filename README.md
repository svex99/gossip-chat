# gossip-chat

Implementación de un chat de grupo usando un método gossip para enviar los mensajes entre los clientes.

Cada cliente descubre los demás clientes de la red haciendo multicast y mantiene registrada las direcciones de los que estén disponible.

En cuanto un cliente recibe un mensaje o decide enviar uno propio, envía el mensaje a todos los clientes disponibles. Detiene el envio del mensaje si uno de los clientes le responde que ya recibió el mensaje de otro cliente, con probabilidad 0.2.

Parámetros necesarios:

```cmd
usage: client.py [-h] [--name NAME] [--inter INTER] [--port PORT]

optional arguments:
  -h, --help     show this help message and exit
  --name NAME    This client name
  --inter INTER  Client interface. Use 'all' for *
  --port PORT    Client port
```

Para ejecutar un cliente:

```cmd
python3 src/client.py --name "John Doe" --inter all --port 8990
```
