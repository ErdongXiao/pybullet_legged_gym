# E. Xiao
# July 2023

import random
import time
import numpy as np
import sys
from gym import spaces
import gym
import os
import math 
import pybullet
import pybullet_data
from datetime import datetime
import pybullet_data
from collections import namedtuple
from attrdict import AttrDict

ROBOT_URDF_PATH = "./aliengo_description/urdf/aliengo.urdf"

# x,y,z distance
def goal_distance(goal_a, goal_b):
    assert goal_a.shape == goal_b.shape
    return np.linalg.norm(np.array([1.25,0.5,0.5,0.25])*(goal_a - goal_b), axis=-1)

# x,y distance
def goal_distance2d(goal_a, goal_b):
    assert goal_a.shape == goal_b.shape
    return np.linalg.norm(goal_a[0:2] - goal_b[0:2], axis=-1)

class AliengoGymEnv(gym.Env):
    def __init__(self,
                 camera_attached=False,
                 # useIK=True,
                 actionRepeat=3,
                 renders=False,
                 maxSteps=100,
                 # numControlledJoints=3, # XYZ, we use IK here!
                 simulatedGripper=False,
                 randObjPos=False,
                 task=0, # here target number
                 learning_param=0):

        self.renders = renders
        self.actionRepeat = actionRepeat

        # setup pybullet sim:
        if self.renders:
            pybullet.connect(pybullet.GUI)
        else:
            pybullet.connect(pybullet.DIRECT)

        pybullet.setTimeStep(1./240.)
        pybullet.setGravity(0,0,-9.8)
        pybullet.setRealTimeSimulation(False)
        # pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_WIREFRAME,1)
        pybullet.resetDebugVisualizerCamera(cameraDistance=1.5, cameraYaw=60, cameraPitch=-30, cameraTargetPosition=[0,0,0])
        pybullet.setPhysicsEngineParameter(enableConeFriction=5000)
        pybullet.setPhysicsEngineParameter(numSolverIterations=30)
        # setup quadruped robot:
        self.end_effector_index = 0
        flags = pybullet.URDF_USE_SELF_COLLISION
        self.aliengo = pybullet.loadURDF(ROBOT_URDF_PATH, [0, 0, 0.5], [0, 0, 0, 1], flags=flags,useFixedBase=0)
        self.num_joints = pybullet.getNumJoints(self.aliengo)
        self.control_joints = ["FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                               "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                               "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
                               "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"]
        self.joint_type_list = ["REVOLUTE", "PRISMATIC", "SPHERICAL", "PLANAR", "FIXED"]
        self.joint_info = namedtuple("jointInfo", ["id", "name", "type", "lowerLimit", "upperLimit", "maxForce", "maxVelocity", "controllable"])
        self.joints = AttrDict()
        self.joint_angles = [-0.1, 0.9, -1.7,
                             0.1, 0.9, -1.7,
                             -0.1, 0.9, -1.7,
                             0.1, 0.9, -1.7]

        # self.joint_angles = [-0.1, 0.8, -1.0,
        #           0.1, 0.4, -1.6,
        #           0.1, 0.4, -1.6,
        #           -0.1, 0.8, -1.0]
        self.quad_action = np.array([0.0]*12)
        for i in range(self.num_joints):
            info = pybullet.getJointInfo(self.aliengo, i)
            jointID = info[0]
            jointName = info[1].decode("utf-8")
            jointType = self.joint_type_list[info[2]]
            jointLowerLimit = info[8]
            jointUpperLimit = info[9]
            jointMaxForce = info[10]
            jointMaxVelocity = info[11]
            controllable = True if jointName in self.control_joints else False
            info = self.joint_info(jointID, jointName, jointType, jointLowerLimit, jointUpperLimit, jointMaxForce, jointMaxVelocity, controllable)
            if info.type == "REVOLUTE" or info.type == "PRISMATIC":
                pybullet.setJointMotorControl2(self.aliengo, info.id, pybullet.VELOCITY_CONTROL, targetVelocity=0, force=0)
            self.joints[info.name] = info

        # object:
        self.plane = pybullet.loadURDF("plane.urdf")
        # self.initial_obj_pos = [0.8, 0.1, 0.0] # initial object pos
        # self.obj = pybullet.loadURDF(CUBE_URDF_PATH, self.initial_obj_pos)

        self.name = 'AliengoGymEnv'
        # self.simulatedGripper = simulatedGripper
        self.action_dim = 12
        self.stepCounter = 0
        self.maxSteps = maxSteps
        self.terminated = False
        # self.randObjPos = randObjPos
        self.observation = np.array(0)

        self.task = task
        self.learning_param = learning_param
     
        self._action_bound = 1.0 # delta limits
        action_high = np.array([self._action_bound] * self.action_dim)
        self.action_space = spaces.Box(-action_high, action_high, dtype='float32')
        self.reset()
        high = np.array([10]*self.observation.shape[0])
        self.observation_space = spaces.Box(-high, high, dtype='float32')

    def set_joint_angles(self, joint_angles):
        poses = []
        indexes = []
        forces = []

        for i, name in enumerate(self.control_joints):
            joint = self.joints[name]
            poses.append(joint_angles[i])
            indexes.append(joint.id)
            forces.append(joint.maxForce)

        pybullet.setJointMotorControlArray(
            self.aliengo, indexes,
            pybullet.POSITION_CONTROL,
            targetPositions=joint_angles,
            targetVelocities=[0]*len(poses),
            positionGains=[0.05]*len(poses),
            forces=forces
        )

    def get_joint_angles(self):
        j = pybullet.getJointStates(self.aliengo, [1,2,3,4,5,6,7,8,9,10,11,12])
        joints_vel = [i[1] for i in j]

        return joints_vel
    

    def check_collisions(self):
        collisions = pybullet.getContactPoints()
        if len(collisions) > 0:
            # print("[Collision detected!] {}".format(datetime.now()))
            return True
        return False


    # def calculate_ik(self, position, orientation):
    #     quaternion = pybullet.getQuaternionFromEuler(orientation)
    #     # print(quaternion)
    #     # quaternion = (0,1,0,1)
    #     lower_limits = [-math.pi]*6
    #     upper_limits = [math.pi]*6
    #     joint_ranges = [2*math.pi]*6
    #     # rest_poses = [0, -math.pi/2, -math.pi/2, -math.pi/2, -math.pi/2, 0]
    #     rest_poses = [(-0.34, -1.57, 1.80, -1.57, -1.57, 0.00)] # rest pose of our aliengo robot

    #     joint_angles = pybullet.calculateInverseKinematics(
    #         self.aliengo, self.end_effector_index, position, quaternion, 
    #         jointDamping=[0.01]*6, upperLimits=upper_limits, 
    #         lowerLimits=lower_limits, jointRanges=joint_ranges, 
    #         restPoses=rest_poses
    #     )
    #     return joint_angles
       
        
    def get_current_pose(self):
        linkstate = pybullet.getLinkState(self.aliengo, self.end_effector_index, computeForwardKinematics=True)
        position, orientation = linkstate[0], linkstate[1]
        return (position, orientation)


    def reset(self):
        self.stepCounter = 0
        self.terminated = False
        self.aliengo_orn = [0.0, 0.0, 0.0]

        # pybullet.addUserDebugText('X', self.obj_pos, [0,1,0], 1) # display goal
        # if self.randObjPos:
        # self.initial_obj_pos = [0.6+random.random()*0.1, 0.1+random.random()*0.1, 0.0]
        # pybullet.resetBasePositionAndOrientation(self.obj, self.initial_obj_pos, [0.,0.,0.,1.0]) # reset object pos

        # reset robot simulation and position:
        pybullet.resetBasePositionAndOrientation(self.aliengo, [0, 0, 0.5], [0, 0, 0, 1])
        pybullet.resetBaseVelocity(self.aliengo, [0.0, 0, 0.], [0, 0, 0])
        self.set_joint_angles(self.joint_angles)

        # step simualator:
        for i in range(100):
            pybullet.stepSimulation()

        # get obs and return:
        self.getExtendedObservation()
        return self.observation
    
    
    def step(self, action):
        # action = np.concatenate((np.array(action)[0:3]*np.array([0.01, 0.6, 1.2]), np.array(action)[3:6]*np.array([0.01, 0.6, 1.2]), np.array(action)[3:6]*np.array([0.01, 0.6, 1.2]), np.array(action)[0:3]*np.array([0.01, 0.6, 1.2])))
        # quad_action = 0.025 * np.array(list(action)+list(action)[3:6]+list(action)[0:3]).astype(float)
        self.quad_action = 0.22 * action.astype(float)
        # arm_action = 0.1 * action[0:self.action_dim-1].astype(float) # dX, dY, dZ - range: [-1,1]
        # gripper_action = action[self.action_dim-1].astype(float) # gripper - range: [-1=closed,1=open]

        # get current position:
        # cur_p = self.get_current_pose()
        # add delta position:
        # new_p = np.array(cur_p[0]) + arm_action
        # actuate: 
        # joint_angles = self.calculate_ik(new_p, self.aliengo_orn) # XYZ and angles set to zero

        self.set_joint_angles(self.quad_action + self.joint_angles)
        # step simualator:
        for i in range(self.actionRepeat):
            pybullet.stepSimulation()
            if self.renders: time.sleep(1./240.)
        
        self.getExtendedObservation()
        reward = self.compute_reward(self.achieved_goal, self.desired_goal, None)
        done = self.my_task_done()

        info = {'is_success': False}
        if self.terminated == self.task:
            info['is_success'] = True

        self.stepCounter += 1

        return self.observation, reward, done, info


    # observations are: arm (tip/tool) position, arm acceleration, ...
    def getExtendedObservation(self):
        # sensor values:
        # js = self.get_joint_angles()

        tool_pos = self.get_current_pose()[0] # XYZ, no angles
        self.obj_vel, self.obj_ang_vel = pybullet.getBaseVelocity(self.aliengo)
        self.obj_pos, self.obj_orn = pybullet.getBasePositionAndOrientation(self.aliengo)
        # self.obj_pos = (2.0, 0, 0.38)
        objects = np.concatenate((self.obj_vel, [self.obj_pos[2]]))
        goal = (0.45, 0, 0., 0.34)
        # print(self.obj_pos[2])
        # self.observation = np.array(np.concatenate((self.obj_vel, [self.obj_pos[2]], self.joint_angles + self.quad_action, [0.]*33)))
        # self.observation = np.array(np.concatenate((self.obj_vel, self.obj_pos, self.obj_orn, self.joint_angles + self.quad_action)))
        self.observation = np.array(np.concatenate((self.obj_ang_vel, 
                                                    np.array([0., 0., -0.98]),
                                                    np.array(goal[0:3]),
                                                    self.quad_action, 
                                                    self.get_joint_angles(),
                                                    self.quad_action,
                                                    np.array([1, 0., 0, 1.]))
                                                    ))
        self.achieved_goal = np.array(np.concatenate((objects, tool_pos)))
        self.desired_goal = np.array(goal)


    def my_task_done(self):
        # NOTE: need to call compute_reward before this to check termination!
        c = (self.terminated == True or self.stepCounter > self.maxSteps)
        return c


    def compute_reward(self, achieved_goal, desired_goal, info):
        reward = np.zeros(1)
 
        # grip_pos = achieved_goal[-3:]
            
        self.target_dist = goal_distance(achieved_goal[0:4], desired_goal)
        # print(grip_pos, desired_goal, self.target_dist)

        # check approach velocity:
        # tv = self.tool.getVelocity()
        # approach_velocity = np.sum(tv)

        # print(approach_velocity)
        # input()

        reward += -self.target_dist * 10

        # task 0: reach object:
        if self.target_dist < 0.0005 * self.learning_param:# and approach_velocity < 0.05:
            self.terminated = True
            # print('Successful!')
        # if self.obj_pos[2]<0.2:
        #     reward += -1000
        #     self.terminated = True
        # reward += -0.005 * np.linalg.norm(self.quad_action)
        # penalize if it tries to go lower than desk / platform collision:
        # if grip_trans[1] < self.desired_goal[1]-0.08: # lower than position of object!
            # reward[i] += -1
            # print('Penalty: lower than desk!')

        # check collisions:
        if self.check_collisions(): 
            reward += -1
            # print('Collision!')

        # print(target_dist, reward)
        # input()

        return reward