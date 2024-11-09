# TP65S-receiver-mpy

## Description
Receive temperature data with MicroPython from ThermoPro TP65s outdoor temperature sensor with the RX470C-V01 module.
The RX470C-V01 module is a low cost (~2 €) 433 MHz receiver for use with microcontrollers (MCUs).

## Hardware Setup
The RX470C-V01 module (RX) only needs one GPIO pin for data transmission.
It can be supplied with either 5V or 3.3V.
RX has two identical digital output (DO) pins, either of them may be used.


Exemplary connections:
- RX_GND --> MCU_GND
- RX_VCC --> MCU_3V3
- RX_DO  --> MCU_GPIO14
