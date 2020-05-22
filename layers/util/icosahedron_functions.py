import torch.nn as nn
from .conversions import *
from .grids import *
from _spherical_distortion_ext._enums import InterpolationType
import _spherical_distortion_ext._mesh as _mesh

# Expose the TriangleMesh class and Icosphere subclass
TriangleMesh = _mesh.TriangleMesh
Icosphere = _mesh.Icosphere

# -----------------------------------------------------------------------------


def generate_icosphere(order=0):
    return _mesh.Icosphere(order)


# -----------------------------------------------------------------------------


def compute_num_vertices(order):
    '''Computes the number of vertices for a given icosphere order'''
    v = 12 * (4**order)
    for i in range(order):
        v -= 6 * (4**i)
    return v


# -----------------------------------------------------------------------------


def compute_num_faces(order):
    '''Computes the number of vertices for a given icosphere order'''
    return 20 * (4**order)


# -----------------------------------------------------------------------------

# =============================================================================
# KERNEL MAPS
# -----------------------------------------------------------------------------
# Kernel maps are of shape (OH, OW, K, 2) or (OH, OW, K, num_interp_pts, 2).
# To be used with Mapped Convolutions
# =============================================================================


def gnomonic_kernel(spherical_coords, kh, kw, res_lat, res_lon):
    '''
    Creates gnomonic filters of shape (kh, kw) with spatial resolutions given by (res_lon, res_lat) and centers them at each coordinate given by <spherical_coords>

    spherical_coords: H, W, 2 (lon, lat)
    kh: vertical dimension of filter
    kw: horizontal dimension of filter
    res_lat: vertical spatial resolution of filter
    res_lon: horizontal spatial resolution of filter
    '''

    lon = spherical_coords[..., 0]
    lat = spherical_coords[..., 1]
    num_samples = spherical_coords.shape[0]

    # Kernel
    x = torch.zeros(kh * kw)
    y = torch.zeros(kh * kw)
    for i in range(kh):
        cur_i = i - (kh // 2)
        for j in range(kw):
            cur_j = j - (kw // 2)
            # Project the sphere onto the tangent plane
            x[i * kw + j] = cur_j * res_lon
            y[i * kw + j] = cur_i * res_lat

    # Center the kernel if dimensions are even
    if kh % 2 == 0:
        y += res_lat / 2
    if kw % 2 == 0:
        x += res_lon / 2

    # Equalize views
    lat = lat.view(1, num_samples, 1)
    lon = lon.view(1, num_samples, 1)
    x = x.view(1, 1, kh * kw)
    y = y.view(1, 1, kh * kw)

    # Compute the projection back onto sphere
    rho = (x**2 + y**2).sqrt()
    nu = rho.atan()
    out_lat = (nu.cos() * lat.sin() + y * nu.sin() * lat.cos() / rho).asin()
    out_lon = lon + torch.atan2(
        x * nu.sin(),
        rho * lat.cos() * nu.cos() - y * lat.sin() * nu.sin())

    # If kernel has an odd-valued dimension, handle the 0 case which resolves to NaN above
    if kh % 2 == 1:
        out_lat[..., [(kh // 2) * kw + kw // 2]] = lat
    if kw % 2 == 1:
        out_lon[..., [(kh // 2) * kw + kw // 2]] = lon

    # Compensate for longitudinal wrap around
    out_lon = ((out_lon + math.pi) % (2 * math.pi)) - math.pi

    # Return (1, num_samples, kh*kw, 2) map at locations given by <spherical_coords>
    return torch.stack((out_lon, out_lat), -1)


# -----------------------------------------------------------------------------


def gnomonic_kernel_from_sphere(icosphere,
                                kh,
                                kw,
                                res_lat,
                                res_lon,
                                source='vertex'):
    '''
    Returns a map of gnomonic filters with shape (kh, kw) and spatial resolution (res_lon, res_lat) centered at each vertex (or face) of the provided icosphere. Sample locations are given by spherical coordinates

    icosphere: icosphere object
    Kh: scalar height of planar kernel
    Kw: scalar width of planar kernel
    res_lat: scalar latitude resolution of kernel
    res_lon: scalar longitude resolution of kernel
    source: {'face' or 'vertex'}

    returns 1 x {F,V} x kh*kw x 2 sampling map per mesh element in spherical coords
    '''

    # Get lat/lon centers of convolution
    if source == 'face':
        spherical_coords = convert_3d_to_spherical(
            icosphere.get_face_barycenters())
        num_samples = icosphere.num_faces()
    elif source == 'vertex':
        spherical_coords = convert_3d_to_spherical(icosphere.get_vertices())
        num_samples = icosphere.num_vertices()
    else:
        print('Invalid source ({})'.format(source))
        exit()

    return gnomonic_kernel(spherical_coords, kh, kw, res_lat, res_lon)


# -----------------------------------------------------------------------------


def vertex_to_vertex_kernel_map(icosphere, kh, kw, order, nearest=False):
    '''
    Returns a map of the vertices and barycentric weights for convolutional filters of shape (kh, kw) that sample from an icosphere of order <order>, and store the result in each vertex of the provided <icosphere>.

    First creates a gnomonic kernel projection for the vertices of the icosphere passed in. Then finds the projection of this kernel onto an icosphere of an order given by the parameter <order>. Returns the vertices that define the triangle onto which each point projects, as well as the barycentric weights for each vertex.

    icosphere: icosphere object whose vertices represent locations where
        filter is applied
    kh: height dimension of filter
    kw: width dimension of filter
    order: order of the icosphere onto which the filter is applied
        (if larger than the order of the passed-in icosphere, this represents a downsampling map; conversely if smaller, this is an upsampling operation)

    returns: vertices (1, V, kh*kw, 3, 2)
             barycentric weights (1, V, kh*kw, 3)

    '''

    # Get the (1, V, kh*kw, 2) map of spherical coordinates corresponding to the gnomonic kernel at the vertices of the sampling icosphere
    ico_res = icosphere.get_angular_resolution()
    spherical_sample_map = gnomonic_kernel_from_sphere(
        icosphere, kh, kw, ico_res, ico_res, source='vertex')

    # Get faces onto which this map is projected
    # V is (1, V, kh*kw, 3)
    # W is (1, V, kh*kw, 3)
    _, V, W = _mesh.get_icosphere_convolution_operator(
        spherical_sample_map, generate_icosphere(order), True, nearest)

    # Stack the vertices with a tensor of zeros because mapped convolution expects 2 values in the last dimension
    V = torch.stack((V, torch.zeros_like(V)), -1)

    return V.float(), W.float()


# =============================================================================
# RESAMPLE MAPS
# -----------------------------------------------------------------------------
# Resample maps are of shape (OH, OW, 2) or (OH, OW, num_interp_pts, 2).
# To be used with Resample and Unresample operations, as opposed to the kernel
# maps defined above, which are for use with Mapped Convolutions
# =============================================================================


def faces_to_equirectangular_resample_map(icosphere, image_shape):
    '''Returns a resample map where each face is associated with a sampling location in spherical coordinates'''
    return convert_spherical_to_image(
        convert_3d_to_spherical(icosphere.get_face_barycenters()), image_shape)


# -----------------------------------------------------------------------------


def vertices_to_equirectangular_resample_map(icosphere, image_shape):
    '''Returns a resample map where each vertex is associated with a sampling location in spherical coordinates'''
    return convert_spherical_to_image(
        convert_3d_to_spherical(icosphere.get_vertices()), image_shape)


# -----------------------------------------------------------------------------


def sphere_to_image_resample_map(order, image_shape, nearest=False):
    '''
    Returns a resample map where the vertices and barycentric weights of an icosphere of order <order> are associated with each pixel of an equirectangular image of size <image_shape>. Used for resampling from a sphere to an image or unresampling an image to a sphere.

    It first creates a meshgrid of spherical coordinates pertaining to the image. Then projects that grid onto an icosphere of an order given by parameter <order>. Returns the vertices that define the triangle onto which each point projects, as well as the barycentric weights for each vertex. If nearest is True, set the maximum barycentric weight as 1 and the others to be 0

    returns: vertices (OH, OW, 3, 2)
             barycentric weights (OH, OW, 3)
    '''

    # Creates a map of spherical coordinates corresponding to the center of each pixel in the image
    spherical_sample_map = torch.stack(spherical_meshgrid(image_shape), -1)

    # Get faces onto which this map is projected
    # V is (1, V, kh*kw, 3)
    # W is (1, V, kh*kw, 3)
    _, V, W = _mesh.get_icosphere_convolution_operator(
        spherical_sample_map, generate_icosphere(order), False, nearest)

    # Stack the vertices with a tensor of zeros because mapped convolution expects 2 values in the last dimension
    V = torch.stack((V, torch.zeros_like(V)), -1)

    return V.float(), W.float()


# -----------------------------------------------------------------------------


def sphere_to_cube_resample_map(order, cube_dim, nearest=False):
    '''
    Returns a resample map where the vertices and barycentric weights of an icosphere of order <order> are associated with each pixel of a cube map with dimension <cube_dim>. Used for resampling from a sphere to a cube map or unresampling a cube map to a sphere.

    It first creates a meshgrid of spherical coordinates pertaining to the cube map image. Then projects that grid onto an icosphere of an order given by parameter <order>. Returns the vertices that define the triangle onto which each point projects, as well as the barycentric weights for each vertex. If nearest is True, set the maximum barycentric weight as 1 and the others to be 0

    returns: vertices (OH, OW, 3, 2)
             barycentric weights (OH, OW, 3)
    '''

    # Creates a map of spherical coordinates corresponding to the center of each pixel in the image
    u, v, index = cube_meshgrid(cube_dim)
    spherical_sample_map = convert_3d_to_spherical(
        convert_cube_to_3d(torch.stack((u, v), -1), index, cube_dim))

    # Get faces onto which this map is projected
    # V is (1, V, kh*kw, 3)
    # W is (1, V, kh*kw, 3)
    _, V, W = _mesh.get_icosphere_convolution_operator(
        spherical_sample_map, generate_icosphere(order), False, nearest)

    # Stack the vertices with a tensor of zeros because mapped convolution expects 2 values in the last dimension
    V = torch.stack((V, torch.zeros_like(V)), -1)

    return V.float(), W.float()


# -----------------------------------------------------------------------------


def sphere_to_samples_resample_map(sample_map, order, nearest=False):
    '''
    Returns a resample map where the vertices and barycentric weights of an icosphere of order <order> are associated with sample of <sample_map>. Used for resampling from a sphere to an image or unresampling an image to a sphere.

    It first creates a meshgrid of spherical coordinates pertaining to the image. Then projects that grid onto an icosphere of an order given by parameter <order>. Returns the vertices that define the triangle onto which each point projects, as well as the barycentric weights for each vertex. If nearest is True, set the maximum barycentric weight as 1 and the others to be 0

    sample_map: (OH, OW, 2) samples in spherical coordinates
    order: scalar order of icosphere to sample from
    nearest: bool whether to use barycentric interpolation or nearest-vertex

    returns: vertices (OH, OW, 3, 2)
             barycentric weights (OH, OW, 3)
    '''
    # Get faces onto which this map is projected
    # V is (1, V, kh*kw, 3)
    # W is (1, V, kh*kw, 3)
    _, V, W = _mesh.get_icosphere_convolution_operator(
        sample_map, generate_icosphere(order), False, nearest)

    if nearest:
        # Set the max weight to 1 and the others to 1
        W = W.max(-1, keepdim=True)[0] == W

    # Stack the vertices with a tensor of zeros because mapped convolution expects 2 values in the last dimension
    V = torch.stack((V, torch.zeros_like(V)), -1)

    return V.float(), W.float()


# -----------------------------------------------------------------------------


def equirectangular_to_sphere_resample_map(image_shape,
                                           icosphere,
                                           source='vertex'):
    '''
    Returns a resample map where each vertex (or face) of the provided <icosphere> has an associated real-valued pixel location in an equirectangular image of shape <image_shape>. Used for resampling from an image to a sphere.

    image_shape: (H, W)
    icosphere: an icosphere
    source: {'face' or 'vertex'}
    Returns 1 x {F,V} x 2 mapping in pixel coords (x, y) per mesh element
    '''

    # Get each face's barycenter in (lon, lat) format
    if source == 'face':
        samples = convert_3d_to_spherical(icosphere.get_face_barycenters())
    elif source == 'vertex':
        samples = convert_3d_to_spherical(icosphere.get_vertices())
    else:
        print('Invalid source ({})'.format(source))
        exit()

    # Get the mapping functions as (1, num_samples, 2)
    sampling_map = convert_spherical_to_image(samples, image_shape).view(
        1, -1, 2)
    return sampling_map


# -----------------------------------------------------------------------------


def equirectangular_from_cube_resample_map(cube_dim, output_shape):
    """
    Returns a sampling map to produce an equirectangular image from a cube map with shape cube_dim x 6*cube_dim
    """

    # Compute the corresponding UV coordinates and face indices for the equirectangular pixels and then convert the (u, v, idx) coordinates to pixels in the cube map
    return convert_spherical_to_cubemap_pixels(
        torch.stack(spherical_meshgrid(output_shape), -1), cube_dim)


# -----------------------------------------------------------------------------


def sphere_from_cube_resample_map(cube_dim, order):
    """
    Returns a sampling map to produce an <order> icosphere from a cube map with shape cube_dim x 6*cube_dim
    """
    # Compute the corresponding UV coordinates and face indices for the sphere vertices and then convert the (u, v, idx) coordinates to pixels in the cube map
    # Returns 1 x V x 2
    return convert_3d_to_cubemap_pixels(
        generate_icosphere(order).get_vertices(), cube_dim).unsqueeze(0)