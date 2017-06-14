

import logging
import json
import time
import argparse
from functools import partial

import RPi.GPIO as gpio
import zmq


def setup_gpio(gpio_bcm_pin_number):
    gpio.setmode(gpio.BCM)
    gpio.setup(gpio_bcm_pin_number, gpio.OUT)
    gpio.output(gpio_bcm_pin_number, gpio.HIGH)


def activate_relay(gpio_pin, seconds=5):
    """
    this should be async. (it's synchronous right now, but this
    isn't scalable for handling multiple concurrent operations 
    and/or long running operations on a relay.)
    """
    gpio.output(gpio_pin, gpio.LOW)
    time.sleep(seconds)
    gpio.output(gpio_pin, gpio.HIGH)
    
    
def base_process_message(raw_message, gpio_pin=None):
    message = json.loads(raw_message)

    # the bounds checking here is just so we don't "brick" the process
    # for, say, 1000 days, these values shouldn't be hard-coded like this
    # but should probably be configured elsewhere and passed in.
    if ("seconds" in message and
        message["seconds"] is not None and
        0 < message["seconds"] <= 5):
        
        activate_relay(gpio_pin, message["seconds"])
        
    else:
        activate_relay(gpio_pin)
        
    return json.dumps({"status": "OK"})    


if __name__ == '__main__':
    description = ""
    
    parser = argparse.ArgumentParser(usage=None, description=description)
    parser.add_argument("--listen_connection", type=str,
                        default="tcp://127.0.0.1:5555",
                        help=("end point this module will bind to, and "
                              "listen for commands"))

    parser.add_argument("--relay_gpio_pin", type=int,
                        default=17,
                        help=("GPIO pin to be driven by "
                              "module (BCM pin numbering scheme)"))

    args = parser.parse_args()
    
    # Bind to the service endpoint:
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(args.listen_connection)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("starting up.  using GPIO pio: {}"
                .format(args.relay_gpio_pin))
    process_message = partial(base_process_message,
                              gpio_pin=args.relay_gpio_pin)
    while True:
        logger.debug('setting up GPIO on pin: {}...'
                     .format(args.relay_gpio_pin))
        setup_gpio(args.relay_gpio_pin)
        try:
            while True:
                raw_message = socket.recv().decode()
                logger.info("Received REQ: {0}".format(raw_message))
                reply = process_message(raw_message)
                logger.info("Sending REP: {0}".format(reply))
                socket.send_string(reply)

        # need to handle graceful shutdown in here.                
        # except <Graceful Shutdown Event/Exception> as e:
        #     gpio.cleanup()
        #     break
        except KeyboardInterrupt:
            logger.info("shutting down...")
            gpio.cleanup()
            break
        
        except Exception as e:
            logger.error("error encountered while handling request")
            logger.error(e)
            gpio.cleanup()
            socket.send_string(json.dumps({
                "status": "ERROR",
            }))
            
