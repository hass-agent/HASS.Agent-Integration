# HASS.Agent 2 Integration - Media Player & Notifications

### Notice

This integration is intended to work with <a href="https://github.com/hass-agent/HASS.Agent" target="_blank">forked version of HASS.Agent</a>.

While it's **very likely** that it'll also work with the original version, it cannot be guaranteed.

----

## Description

This <a href="https://www.home-assistant.io" target="_blank">Home Assistant</a> integration is the second-half of <a href="https://github.com/hass-agent/HASS.Agent" target="_blank">HASS.Agent</a>, a Windows-based Home Assistant client.

This integration allows HASS.Agent to act as a media player and notification receiver (like Home Assistant Companion Applications). 

All communication is done through MQTT. It supports auto discovery, so you'll see your HASS.Agent devices show up automatically in the integrations page:

![image](https://user-images.githubusercontent.com/81011038/198246059-caa7f1cd-89f7-41f9-989e-724a1a67c2fe.png)

## Features
Windows device acting as a media player (for music and TTS messages):

![image](https://user-images.githubusercontent.com/81011038/198246217-cce288be-bbb7-4c5f-baff-510cc99c30b1.png)

Sending actionable notifications:

![image](https://user-images.githubusercontent.com/81011038/190643738-724dac45-4d03-4a19-a0e6-3a59b5de0aad.png)

## Installation

The supported way to install HASS.Agent integration is through HACS. This version of is ***not yet available in HACS by default and needs to be added as a custom repository***.

If you have the **original version of HASS.Agent integration** installed (either version), **please remove it** before proceeding further and restart Home Assistant.

1. Add "HASS.Agent 2 Integration" repository - https://github.com/hass-agent/HASS.Agent-Integration - as a custom HACS integration repository.
 ![i0mENM](https://github.com/amadeo-alex/HASS.Agent-Integration/assets/68441479/13e0f132-9b01-46f0-97c9-05f33f214aaf)
 <img src="https://github.com/amadeo-alex/HASS.Agent-Integration/assets/68441479/438a0dd7-975f-4cf3-a138-887fd4cf9eee" width="300" />

3. Install "HASS.Agent 2 Integration" from HACS (including restart), as you would with any other integration.
4. Configure HASS.Agent devices when they are discovered.

In case of issues please get in touch <a href="https://discord.gg/JfZj98xqJr" target="_blank">on Discord</a>.

----

[GETTING STARTED GUIDE](https://www.hass-agent.io/latest/getting-started/)

For more help and examples, check [the documentation](https://www.hass-agent.io/latest/), <a href="https://discord.gg/JfZj98xqJr" target="_blank">join on Discord</a> or visit the <a href="https://community.home-assistant.io/t/hass-agent-a-new-windows-based-client-to-receive-notifications-perform-quick-actions-and-much-more/369094" target="_blank">dedicated HA forum thread (for original version)</a>.

----

Thanks [@fillefilip8](https://github.com/fillefilip8) for developing the original version!
