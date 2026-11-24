# Automation ideas

Replace `sensor.jlr_…` with your own entity IDs: Settings → Devices & services → JLR Data Hub → your car.

??? example "Tell me when charging finishes"
    ```yaml
    automation:
      - alias: Car charged
        triggers:
          - trigger: state
            entity_id: sensor.jlr_vehicle_charging_state
            to: complete
        actions:
          - action: notify.mobile_app_your_phone
            data:
              message: "Charged to {{ states('sensor.jlr_vehicle_battery') }}%"
    ```

??? example "Remind me if the car's left unlocked at night"
    ```yaml
    automation:
      - alias: Car unlocked at night
        triggers:
          - trigger: time
            at: "22:30:00"
        conditions:
          - condition: state
            entity_id: binary_sensor.jlr_vehicle_lock
            state: "on"   # on = unlocked
        actions:
          - action: notify.mobile_app_your_phone
            data:
              message: The car is unlocked.
    ```

    Remember the lock state can be [a few minutes behind](freshness.md).

??? example "Warn me when the 12 V battery is low"
    ```yaml
    automation:
      - alias: 12 V battery low
        triggers:
          - trigger: numeric_state
            entity_id: sensor.jlr_vehicle_12_v_battery
            below: 11.9
            for: "00:30:00"
        actions:
          - action: notify.mobile_app_your_phone
            data:
              message: "The car's 12 V battery is at {{ states('sensor.jlr_vehicle_12_v_battery') }} V."
    ```

    While driving or charging it reads about 14 V. Parked and healthy, it rests around 12.4–12.8 V.

??? example "Plug in reminder"
    ```yaml
    automation:
      - alias: Plug the car in
        triggers:
          - trigger: time
            at: "21:00:00"
        conditions:
          - condition: numeric_state
            entity_id: sensor.jlr_vehicle_battery
            below: 40
          - condition: state
            entity_id: binary_sensor.jlr_vehicle_plugged_in
            state: "off"
        actions:
          - action: notify.mobile_app_your_phone
            data:
              message: "Battery at {{ states('sensor.jlr_vehicle_battery') }}% and not plugged in."
    ```
