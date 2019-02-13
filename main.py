import sys
import math
import numpy as np

import Box2D

import gym
from gym import spaces
from gym.utils import colorize, seeding, EzPickle

import pyglet
from pyglet import gl

from Objects.Robot import Robot
from Objects.Bullet import Bullet
from Referee.ICRAMap import ICRAMap
from Referee.BuffArea import AllBuffArea
from Referee.ICRAContactListener import ICRAContactListener
from SupportAlgorithm.DetectCallback import detectCallback

STATE_W = 96   # less than Atari 160x192
STATE_H = 96
VIDEO_W = 600
VIDEO_H = 400
WINDOW_W = 1200
WINDOW_H = 1000

SCALE = 40.0        # Track scale
PLAYFIELD = 400/SCALE  # Game over boundary
FPS = 30
ZOOM = 2.7        # Camera zoom
ZOOM_FOLLOW = True       # Set to False for fixed view (don't use zoom)

SCAN_RANGE = 5

class ICRAField(gym.Env, EzPickle):
    metadata = {
        'render.modes': ['human', 'rgb_array', 'state_pixels'],
        'video.frames_per_second': FPS
    }

    def __init__(self):
        EzPickle.__init__(self)
        self.seed()
        self.contactListener_keepref = ICRAContactListener(self)
        self.world = Box2D.b2World(
            (0, 0), contactListener=self.contactListener_keepref)
        self.viewer = None
        self.invisible_state_window = None
        self.invisible_video_window = None
        self.robots = {}
        self.map = None
        self.buff_areas = None
        self.bullets = None
        self.detect_callback = detectCallback()

        self.reward = 0.0
        self.prev_reward = 0.0
        self.action_space = spaces.Box(np.array([-1, -1, 0, -1]),
                                       np.array([+1, +1, +1, +1]), dtype=np.float32)
        # transverse, gas, shoot, move head
        self.observation_space = spaces.Box(
            low=0, high=255, shape=(STATE_H, STATE_W, 3), dtype=np.uint8)

    def seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def _destroy(self):
        for robot_name in self.robots.keys():
            self.robots[robot_name].destroy()
        self.robots = {}
        if self.map:
            self.map.destroy()
        self.map = None
        if self.bullets:
            self.bullets.destroy()
        self.bullets = None

    def reset(self):
        self._destroy()
        self.reward = 0.0
        self.prev_reward = 0.0
        self.t = 0.0
        self.human_render = False

        self.robots = {}
        for robot_name, x in zip(["robot_0", "robot_1"], [0.5, 3.5]):
            self.robots[robot_name] = Robot(
                self.world, -np.pi/2, x, 4.5, robot_name, 0, 'red')
        self.map = ICRAMap(self.world)
        self.bullets = Bullet(self.world)
        self.buff_areas = AllBuffArea()

        return self.step(None)[0]

    def collision_step(self):
        collision_bullet_robot = self.contactListener_keepref.collision_bullet_robot
        collision_bullet_wall = self.contactListener_keepref.collision_bullet_wall
        collision_robot_wall = self.contactListener_keepref.collision_robot_wall
        for bullet, robot in collision_bullet_robot:
            self.bullets.destroyById(bullet)
            self.robots[robot].loseHealth(50)
        for bullet in collision_bullet_wall:
            self.bullets.destroyById(bullet)
        for robot in collision_robot_wall:
            self.robots[robot].loseHealth(10)
        self.contactListener_keepref.clean()

    def action_step(self, robot_name, action):
        self.robots[robot_name].moveTransverse(-action[0])
        self.robots[robot_name].moveAheadBack(action[1])
        if action[2] > 0.99 and int(self.t*FPS) % (FPS/5) == 1:
            init_angle, init_pos = self.robots[robot_name].getGunAnglePos()
            self.bullets.shoot(init_angle, init_pos)
        self.robots[robot_name].rotateCloudTerrance(action[3])
        self.robots[robot_name].turnLeftRight(action[4])

    def detect_step(self):
        detected = []
        for i in range(-10, 10):
            angle, pos = self.robots["robot_0"].getGunAnglePos()
            angle += i/180*math.pi
            p1 = (pos[0] + 0.5*math.cos(angle), pos[1] + 0.5*math.sin(angle))
            p2 = (pos[0] + SCAN_RANGE*math.cos(angle), pos[1] + SCAN_RANGE*math.sin(angle))
            self.world.RayCast(self.detect_callback, p1, p2)
            u = self.detect_callback.userData
            if u in self.robots.keys():
                #target = self.detect_callback.point
                #target_angle = math.atan2(target[1], target[0])
                #print("angle: {}, target angle: {}".format(angle, target_angle))
                #self.robots["robot_0"].setCloudTerrance(angle-math.pi/2)
                detected.append(angle)
                #break
        if detected:
            angle = sum(detected) / len(detected)
            self.robots["robot_0"].setCloudTerrance(angle)

    def step(self, action):
        self.collision_step()
        if action is not None:
            self.action_step("robot_0", action)

        self.detect_step()
        self.buff_areas.detect([self.robots["robot_0"], self.robots["robot_1"]])

        for robot_name in self.robots.keys():
            self.robots[robot_name].step(1.0/FPS)
        self.world.Step(1.0/FPS, 6*30, 2*30)
        self.t += 1.0/FPS

        self.state = self.render("state_pixels")

        step_reward = 0
        done = False
        if action is not None:  # First step without action, called from reset()
            self.reward -= 0.1
            step_reward = self.reward - self.prev_reward
            self.prev_reward = self.reward
            x, y = self.robots["robot_0"].hull.position
            if abs(x) > PLAYFIELD or abs(y) > PLAYFIELD:
                done = True
                step_reward = -100

        return self.state, step_reward, done, {}

    def render(self, mode='human'):
        if self.viewer is None:
            from gym.envs.classic_control import rendering
            self.viewer = rendering.Viewer(WINDOW_W, WINDOW_H)
            self.score_label = pyglet.text.Label('0000', font_size=36,
                                                 x=20, y=WINDOW_H*2.5/40.00, anchor_x='left', anchor_y='center',
                                                 color=(255, 255, 255, 255))
            self.health_label = pyglet.text.Label('0000', font_size=16,
                                                  x=520, y=WINDOW_H*2.5/40.00, anchor_x='left', anchor_y='center',
                                                  color=(255, 255, 255, 255))
            self.transform = rendering.Transform()

        if "t" not in self.__dict__:
            return  # reset() not called yet

        zoom = ZOOM*SCALE
        zoom_state = ZOOM*SCALE*STATE_W/WINDOW_W
        zoom_video = ZOOM*SCALE*VIDEO_W/WINDOW_W
        #scroll_x = self.car0.hull.position[0]
        #scroll_y = self.car0.hull.position[1]
        #angle = -self.car0.hull.angle
        scroll_x = 4.0
        scroll_y = 0.0
        angle = 0
        #vel = self.car0.hull.linearVelocity
        # if np.linalg.norm(vel) > 0.5:
        #angle = math.atan2(vel[0], vel[1])
        self.transform.set_scale(zoom, zoom)
        self.transform.set_translation(
            WINDOW_W/2 - (scroll_x*zoom*math.cos(angle) -
                          scroll_y*zoom*math.sin(angle)),
            WINDOW_H/4 - (scroll_x*zoom*math.sin(angle) + scroll_y*zoom*math.cos(angle)))
        # self.transform.set_rotation(angle)

        self.map.draw(self.viewer)
        for robot_name in self.robots.keys():
            self.robots[robot_name].draw(self.viewer, mode != "state_pixels")
        self.bullets.draw(self.viewer)

        arr = None
        win = self.viewer.window
        if mode != 'state_pixels':
            win.switch_to()
            win.dispatch_events()
        if mode == "rgb_array" or mode == "state_pixels":
            win.clear()
            t = self.transform
            if mode == 'rgb_array':
                VP_W = VIDEO_W
                VP_H = VIDEO_H
            else:
                VP_W = STATE_W
                VP_H = STATE_H
            gl.glViewport(0, 0, VP_W, VP_H)
            t.enable()
            for geom in self.viewer.onetime_geoms:
                geom.render()
            t.disable()
            # TODO: find why 2x needed, wtf
            self.render_indicators(WINDOW_W, WINDOW_H)
            image_data = pyglet.image.get_buffer_manager().get_color_buffer().get_image_data()
            arr = np.fromstring(image_data.data, dtype=np.uint8, sep='')
            arr = arr.reshape(VP_H, VP_W, 4)
            arr = arr[::-1, :, 0:3]

        # agent can call or not call env.render() itself when recording video.
        if mode == "rgb_array" and not self.human_render:
            win.flip()

        if mode == 'human':
            self.human_render = True
            win.clear()
            t = self.transform
            gl.glViewport(0, 0, WINDOW_W, WINDOW_H)
            t.enable()
            self.render_background()
            for geom in self.viewer.onetime_geoms:
                geom.render()
            t.disable()
            self.render_indicators(WINDOW_W, WINDOW_H)
            win.flip()

        self.viewer.onetime_geoms = []
        return arr

    def close(self):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

    def render_background(self):
        gl.glBegin(gl.GL_QUADS)
        gl.glColor4f(0.4, 0.8, 0.4, 1.0)
        gl.glVertex3f(-PLAYFIELD, +PLAYFIELD, 0)
        gl.glVertex3f(+PLAYFIELD, +PLAYFIELD, 0)
        gl.glVertex3f(+PLAYFIELD, -PLAYFIELD, 0)
        gl.glVertex3f(-PLAYFIELD, -PLAYFIELD, 0)
        gl.glColor4f(0.4, 0.9, 0.4, 1.0)
        k = PLAYFIELD/20.0
        for x in range(-20, 20, 2):
            for y in range(-20, 20, 2):
                gl.glVertex3f(k*x + k, k*y + 0, 0)
                gl.glVertex3f(k*x + 0, k*y + 0, 0)
                gl.glVertex3f(k*x + 0, k*y + k, 0)
                gl.glVertex3f(k*x + k, k*y + k, 0)
        gl.glEnd()
        self.buff_areas.render(gl)

        # self.render_buff_area(self.map.buff_area)

    # def render_buff_area(self, buff_area):
    #     gl.Begin(gl.GL_QUADS)
    #     gl.glColor4f(1.0, 0.0, 0.0, 0.5)
    #     for pos, box in buff_area:
    #         pass

    def render_indicators(self, W, H):
        self.score_label.text = "%04i" % self.reward
        self.health_label.text = "health left Car0 : {} Car1: {} ".format(
            self.robots["robot_0"].health, self.robots["robot_1"].health)
        self.score_label.draw()
        self.health_label.draw()


if __name__ == "__main__":
    from pyglet.window import key
    # action[7] for steer, gas, shoot, move head, rotation
    a = np.array([0.0, 0.0, 0.0, 0.0, 0.0])

    def key_press(k, mod):
        global restart
        if k == 0xff0d: restart = True
        if k == key.A: a[0] = +1.0
        if k == key.D: a[0] = -1.0
        if k == key.W: a[1] = +1.0
        if k == key.S: a[1] = -1.0
        if k == key.SPACE: a[2] = +1.0
        if k == key.Q: a[4] = +0.5
        if k == key.E: a[4] = -0.5
        if k == key.Z: a[3] = +2
        if k == key.C: a[3] = -2

    def key_release(k, mod):
        if k == key.A: a[0] = 0
        if k == key.D: a[0] = 0
        if k == key.W: a[1] = 0
        if k == key.S: a[1] = 0
        if k == key.SPACE: a[2] = 0
        if k == key.Q: a[4] = 0
        if k == key.E: a[4] = 0
        if k == key.Z: a[3] = 0
        if k == key.C: a[3] = 0

    env = ICRAField()
    env.render()
    record_video = False
    if record_video:
        env.monitor.start('/tmp/video-test', force=True)
    env.viewer.window.on_key_press = key_press
    env.viewer.window.on_key_release = key_release
    while True:
        env.reset()
        total_reward = 0.0
        steps = 0
        restart = False
        while True:
            s, r, done, info = env.step(a)
            total_reward += r
            if steps % 200 == 0 or done:
                print("\naction " + str(["{:+0.2f}".format(x) for x in a]))
                print("step {} total_reward {:+0.2f}".format(steps, total_reward))
                #import matplotlib.pyplot as plt
                # plt.imshow(s)
                # plt.savefig("test.jpeg")
            steps += 1
            # Faster, but you can as well call env.render() every time to play full window.
            if not record_video:
                env.render()
            if done or restart:
                break
    env.close()
