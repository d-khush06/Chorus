# Camera & Live Watch Setup Guide

This guide covers setting up a local IP camera (such as the Dahua DH-H3A-U) for Live Watch, especially when the camera and backend are on different networks using Tailscale.

## 1. Finding the Camera's IP Address
If your camera is connected to a local Wi-Fi or mobile hotspot, its IP address might change when reconnecting. 
To find the IP:
- **Using Nmap:** Run `nmap -sn 192.168.1.0/24` (replace with your subnet) from a device on the same network. Look for the Dahua device.
- **Using Companion App:** Check the Dahua companion app or your router's "Connected Devices" list.

## 2. RTSP URL Pattern
For the Dahua DH-H3A-U (Hero A1), the RTSP URL follows this pattern:
```
rtsp://<username>:<password>@<camera_ip>:554/cam/realmonitor?channel=1&subtype=1
```
- **Username:** Usually `admin`.
- **Password:** If your password contains special characters like `@`, you **must URL-encode** them (e.g., `admin@123` becomes `admin%40123`).
- **Subtype:** 
  - `subtype=1` selects the substream (usually H.264, lower resolution), which is perfect for browser preview and low latency. 
  - `subtype=0` selects the main stream (often H.265), which most browsers cannot natively preview.

## 3. Configuration & Security
To prevent unauthorized access (SSRF), you must explicitly allowlist your camera's IP.
1. Open `backend/.env`.
2. Find or add the `ALLOWED_RTSP_TARGETS` variable.
3. Add your camera's bare IP address (e.g., `10.176.102.50`) or a CIDR range.
   ```
   ALLOWED_RTSP_TARGETS=10.176.102.50
   ```
4. **Restart the backend.** No code changes are required.

> **SECURITY REMINDER:** Never commit real camera credentials (IPs, usernames, passwords) to source code or configuration files that are checked into version control. Ensure `.env` is in your `.gitignore`. If you accidentally commit a password, rotate the camera's password immediately.

## 4. Tailscale Subnet Router Setup (Different Networks)
If your backend is running on a different network (e.g., a university Ethernet) than the camera (e.g., a mobile hotspot), you must use a Tailscale Subnet Router.

1. **Advertise the Route (Hotspot Network):**
   Install Tailscale on a device (Linux/Windows) connected to the same hotspot as the camera. Run:
   ```bash
   sudo tailscale up --advertise-routes=<hotspot_subnet>/24
   ```
2. **Approve the Route:**
   Go to your [Tailscale Admin Console](https://login.tailscale.com/admin/machines). Find the routing machine, click `...` -> **Edit route settings**, and toggle the subnet to ON.
3. **Accept the Route (Backend Network):**
   On the machine running the backend app, open Tailscale Preferences and ensure **Use Tailscale subnets** is checked. If on Linux, run `tailscale up --accept-routes`.
   
> **Note on IP Drift:** Mobile hotspots often reassign IPs or entirely change subnets on reconnect. If the hotspot gives out a new subnet (e.g., changes from `192.168.43.0/24` to `10.176.102.0/24`), you must re-advertise the new subnet and re-approve it in the admin console.

## 5. Troubleshooting
- **Connection Timed Out / Camera Not Reachable:** The IP is wrong, the camera is off, or the Tailscale subnet route is not active/approved.
- **401 Unauthorized:** The username or password in the URL is incorrect. Make sure special characters are URL-encoded.
- **Stream loads but shows no video (or gray box):** You are likely trying to stream `subtype=0` (H.265). Browsers do not support H.265 natively via WebRTC/MSE in many cases. Switch to `subtype=1`.
- **SSRF Blocked:** The camera's IP is not in `ALLOWED_RTSP_TARGETS`. Update your `.env` and restart the backend.
