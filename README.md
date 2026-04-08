
## **SDN Flow Rule Timeout Manager using Mininet and Ryu**

---

## **1. Problem Statement**

In Software Defined Networking (SDN), switches rely on flow rules installed by a centralized controller to forward packets. However, if flow rules are not managed properly, they can persist indefinitely and consume limited switch memory, leading to inefficiency and degraded performance.

The problem addressed in this project is:

> How to dynamically manage the lifecycle of flow rules in an OpenFlow-based network to ensure that stale or unused rules are automatically removed.

This project implements a **Flow Rule Timeout Manager** using the Ryu controller and Mininet to demonstrate how flow entries can be controlled using **idle timeout** and **hard timeout** mechanisms.

---

## **2. Setup & Execution Steps**

### **2.1 Prerequisites**

* Fedora Linux
* Python 3
* Mininet (installed from source)
* Ryu controller (installed via pip in virtual environment)
* Open vSwitch

---

### **2.2 Environment Setup**

#### Step 1: Create and activate virtual environment

```bash
python3 -m venv sdn-env-py39
source sdn-env-py39/bin/activate
```

#### Step 2: Install Ryu

```bash
pip install ryu
```

---

### **2.3 Run the Controller**

```bash
ryu-manager controller/timeout_controller.py
```

---

### **2.4 Run Mininet Topology (in a new terminal)**

```bash
sudo mn --custom topology/simple_topo.py --topo simpletopo --controller=remote --switch=ovs
```

---

### **2.5 Test Connectivity**

Inside Mininet:

```bash
h1 ping h2
```

---

### **2.6 Observe Flow Rules**

In another terminal:

```bash
sudo ovs-ofctl dump-flows s1
```

---

## **3. Expected Output**

### **Scenario 1: Continuous Traffic**

* When continuous ping is running between hosts:

  * Flow rules are installed in the switch
  * Packet counters increase
  * Rules remain active

Expected output:
<img width="1394" height="74" alt="case1" src="https://github.com/user-attachments/assets/3691b7f1-fdfa-4572-a4ea-eba221d95e6d" />


---

### **Scenario 2: No Traffic (Idle Timeout)**

* When traffic is stopped:

  * After ~10 seconds (idle timeout), flow rules are removed
  * Switch flow table becomes empty

Expected output:

<img width="771" height="95" alt="case2" src="https://github.com/user-attachments/assets/c9172261-01ed-4baf-9f2c-016c74b430eb" />

---

### **Key Observations**

* Flow rules are dynamically installed by the controller upon receiving packets.
* Idle timeout ensures removal of unused flow entries.
* This prevents stale rules from occupying switch memory.
* The system demonstrates efficient flow lifecycle management in SDN.

---

## **4. Tools Used**

* Mininet (network emulation)
* Ryu Controller (SDN control plane)
* OpenFlow protocol
* Open vSwitch
* Wireshark / tcpdump (optional for validation)

---

## **5. Conclusion**

This project successfully demonstrates how SDN controllers can manage flow rules dynamically using timeout mechanisms. By implementing idle and hard timeouts, the system ensures efficient utilization of switch resources and avoids persistence of stale flow entries.

---

