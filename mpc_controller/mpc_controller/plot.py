import pickle as pkl
import matplotlib.pyplot as plt
import numpy as np
def np_move_avg(a,n,mode="same"):
    return(np.convolve(a, np.ones((n,))/n, mode=mode))
f = open("mpc_obs.pkl", "rb")

data = pkl.load(f)
joint_angles = np.array(data["joint_angles"])
joint_velocity = np.array(data["joint_velocity"])
joint_name = [
    "FR_hip_joint",
    "FR_thigh_joint",
    "FR_calf_joint",
    "FL_hip_joint",
    "FL_thigh_joint",
    "FL_calf_joint",
    "RR_hip_joint",
    "RR_thigh_joint",
    "RR_calf_joint",
    "RL_hip_joint",
    "RL_thigh_joint",
    "RL_calf_joint",
]
plt.figure(1)
for i in range(12):
    # print(i//3+1+4*((i)%3))
    plt.subplot(3,4,i//3+1+4*((i)%3))
    plt.plot(np_move_avg(joint_angles[:,i],23,mode="full")[100:-100])
    plt.title(joint_name[i]+"_angle", loc="center", fontdict={"size":10})
    if i//3+1+4*((i)%3) in [1,5,9]:
        plt.ylabel("[rad]", loc="center", fontdict={"size":10})
    plt.savefig("joint_angles.png")
plt.figure(2)
for i in range(12):
    # print(i//3+1+4*((i)%3))
    plt.subplot(3,4,i//3+1+4*((i)%3))
    plt.plot(np_move_avg(joint_velocity[:,i],23,mode="full")[100:-100])
    plt.title(joint_name[i]+"_vel", loc="center", fontdict={"size":10})
    if i//3+1+4*((i)%3) in [1,5,9]:
        plt.ylabel("[$rad*s^{-1}$]")
    plt.savefig("joint_velocity.png")
plt.show()
plt.show()