import chainer
import chainer.functions as F
import numpy as np
import trimesh.transformations as ttf

from .. import functions as functions_module


class CollisionBasedPoseRefinementLink(chainer.Link):

    def __init__(self, transform, voxel_dim=32, voxel_threshold=2):
        super().__init__()

        self._voxel_dim = voxel_dim
        self._voxel_threshold = voxel_threshold

        quaternion = []
        translation = []
        for transform_i in transform:
            quaternion.append(ttf.quaternion_from_matrix(transform_i))
            translation.append(ttf.translation_from_matrix(transform_i))
        quaternion = np.stack(quaternion).astype(np.float32)
        translation = np.stack(translation).astype(np.float32)

        with self.init_scope():
            self.quaternion = chainer.Parameter(quaternion)
            self.translation = chainer.Parameter(translation)

    def forward(
        self, points, pitch, origin, grid_target, grid_nontarget_empty
    ):
        transform = functions_module.transformation_matrix(
            self.quaternion, self.translation
        )

        points = [
            functions_module.transform_points(p, t)
            for p, t in zip(points, transform)
        ]

        grid = []
        grid_nontarget_empty = [g for g in grid_nontarget_empty]
        for i in range(len(points)):
            grid_i = functions_module.pseudo_occupancy_voxelization(
                points[i],
                pitch=pitch[i],
                origin=origin[i],
                dims=(self._voxel_dim,) * 3,
                threshold=self._voxel_threshold,
            )
            grid.append(grid_i)

            if len(points) <= 1:
                continue
            points_other = F.vstack(
                [p for j, p in enumerate(points) if i != j]
            )
            grid_other = functions_module.pseudo_occupancy_voxelization(
                points_other,
                pitch=pitch[i],
                origin=origin[i],
                dims=(self._voxel_dim,) * 3,
                threshold=self._voxel_threshold,
            )
            grid_nontarget_empty[i] = F.maximum(
                grid_nontarget_empty[i], grid_other
            )
        grid = F.stack(grid)
        grid_nontarget_empty = F.stack(grid_nontarget_empty)

        reward = F.sum(grid * grid_target) / F.sum(grid_target)
        penalty = F.sum(grid * grid_nontarget_empty) / F.sum(grid)
        loss = penalty - reward
        return loss