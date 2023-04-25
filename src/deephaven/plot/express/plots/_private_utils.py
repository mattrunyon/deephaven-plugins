from functools import partial
from typing import Callable
from collections.abc import Generator

from plotly import subplots
from plotly.graph_objects import Figure

from deephaven.table import Table

from ..deephaven_figure import generate_figure, DeephavenFigure, update_traces


def default_callback(
        fig
) -> Figure:
    """
    A default callback that returns the passed fig

    :param fig:
    :return: The same fig
    """
    return fig


def normalize_position(
        position: float,
        chart_start: float,
        chart_range: float
) -> float:
    """
    Normalize a position so that it falls between 0 and 1 (inclusive)

    :param position: The current position
    :param chart_start: The start of the domain the existing chart has
    :param chart_range: The range the existing chart has
    :return:
    """
    return (position - chart_start) / chart_range


def get_new_positions(
        new_domain: list[float],
        positions: list[float],
        chart_domain: list[float]
) -> list[float]:
    """
    Get positions within the new domain of an arbitrary list of positions
    The positions will first be normalized to fall between 0 and 1 inclusive
    using the current chart_domain. Then, the positions are mapped onto
    new_domain.
    For example, if a position is at 0.5, chart_domain is [0, 1] and new_domain
    is [0, 0.6], the new position is 0.3.

    :param new_domain: The new domain to map the points to
    :param positions: The current positions of the points
    :param chart_domain: The current domain of the whole chart
    :return:
    """
    if not isinstance(positions, list):
        positions = [positions]
    new_positions = []
    new_range = new_domain[1] - new_domain[0]
    for position in positions:
        chart_range = chart_domain[1] - chart_domain[0]
        normalized = normalize_position(position, chart_domain[0], chart_range)
        new_position = new_domain[0] + normalized * new_range
        new_positions.append(new_position)
    return new_positions


def resize_domain(
        obj: dict,
        new_domain: dict[str, list[float]]
) -> None:
    """
    Resize the domain of the given object

    :param obj: The object to resize. It should have a "domain" key that
    references a dict that has "x" and "y" keys.
    :param new_domain: The new domain the map the figure to. Contains keys of x
    and y and values of domains, such as [0,0.5]
    keys
    """
    new_domain_x = new_domain.get("x", None)
    new_domain_y = new_domain.get("y", None)
    obj_domain_x = obj["domain"]["x"]
    obj_domain_y = obj["domain"]["y"]
    domain_update = {}
    try:
        # assuming that the whole chart spans [0,1] in both directions as
        # passing a subplot is currently not supported
        if new_domain_x:
            domain_update["x"] = get_new_positions(new_domain_x, obj_domain_x, [0, 1])
        if new_domain_y:
            domain_update["y"] = get_new_positions(new_domain_y, obj_domain_y, [0, 1])
        if domain_update:
            obj.update({"domain": domain_update})
    except ValueError:
        # the obj might not have a domain to resize
        pass


def resize_xy_axis(
        axis: dict,
        new_domain: dict[str, list[float]],
        which: str
) -> None:
    """
    Resize either an x or y axis.

    :param axis: The axis object to resize. It should have a "domain" key.
    :param new_domain: The new domain the map the figure to. Contains keys of x
    and y and values of domains, such as [0,0.5]
    :param which: Either "x" or "y"
    """
    new_domain_x = new_domain.get("x", None)
    new_domain_y = new_domain.get("y", None)
    axis_domain = axis["domain"]
    axis_position = axis.get("position", None)
    axis_update = {}
    try:
        if which == "x":
            if new_domain_x:
                axis_update["domain"] = get_new_positions(new_domain_x, axis_domain, [0, 1])
            if new_domain_y and axis_position is not None:
                axis_update["position"] = get_new_positions(new_domain_y, axis_position, [0, 1])[0]
        else:
            if new_domain_y:
                axis_update["domain"] = get_new_positions(new_domain_y, axis_domain, [0, 1])
            if new_domain_x and axis_position is not None:
                axis_update["position"] = get_new_positions(new_domain_x, axis_position, [0, 1])[0]

        axis.update(axis_update)
    except ValueError:
        # the obj might not have an axis to resize
        pass


def reassign_axes(
        trace: dict,
        axes_remapping: dict[str, str]
) -> None:
    """
    RUpdate the trace with its new axes using with the remapping

    :param trace: The trace to remap axes within
    :param axes_remapping: The mapping of old to new axes
    """
    if 'xaxis' in trace:
        trace.update(xaxis=axes_remapping[trace['xaxis']])

    if 'yaxis' in trace:
        trace.update(yaxis=axes_remapping[trace['yaxis']])

    if 'scene' in trace:
        trace.update(scene=axes_remapping[trace['scene']])

    if 'subplot' in trace:
        trace.update(subplot=axes_remapping[trace['subplot']])

    if 'ternary' in trace:
        trace.update(ternary=axes_remapping[trace['ternary']])


def reassign_attributes(
        axis: dict,
        axes_remapping: dict[str, str]
) -> None:
    """
    Reassign attributes of a layout object using with the remapping

    :param axis: The axis object to remap attributes from
    :param axes_remapping: The mapping of old to new axes
    """
    # anchor can also be free, which does not need to be modified
    if 'anchor' in axis and axis['anchor'] in axes_remapping:
        axis.update(anchor=axes_remapping[axis['anchor']])

    if 'overlaying' in axis and axis['overlaying'] in axes_remapping:
        axis.update(overlaying=axes_remapping[axis['overlaying']])


def resize_axis(
        type_: str,
        old_axis: str,
        axis: dict,
        num: str,
        new_domain: dict[str, list[float]]
) -> tuple[str, str, str]:
    """
    Maps the specified axis to new_domain and returns info to help remap axes

    :param type_: The type of axis to resize
    :param old_axis: The old axis name
    :param axis: The axis object to resize
    :param num: The number (possibly empty) of this axis within the new chart
    :param new_domain: The new domain the map the figure to. Contains keys of x
    and y and values of domains, such as [0,0.5]
    :return: A tuple of new axis name, old axis name (for trace remapping),
    new axis name (for trace remapping). The new axis name isn't always the
    same within the trace as it is in the layout (such as in the case of xaxis
    or yaxis), hence the need for both of the names.
    """
    new_axis = f"{type_}{num}"
    if type_ == 'xaxis' or type_ == 'yaxis':
        which = type_[0]
        resize_xy_axis(axis, new_domain, which)
        old_trace_axis = old_axis.replace(type_, which)
        return new_axis, old_trace_axis, f"{which}{num}"
    else:
        resize_domain(axis, new_domain)
        return new_axis, old_axis, new_axis


def resize(
        fig_data: dict,
        fig_layout: dict,
        new_domain: dict[str, list[float]],
        new_axes_start: dict[str, int],
) -> tuple[dict, dict]:
    """
    Resize a figure into new_domain, reindexing with the indices specified in
    new_axes_start

    :param fig_data: The current figure data
    :param fig_layout: The current figure layout
    :param new_domain: The new domain the map the figure to. Contains keys of x
    and y and values of domains, such as [0,0.5]
    :param new_axes_start: A dictionary containing the start of new indices to
    ensure there is no reindexing collisions
    :return: A tuple of the new figure data, the new figure layout
    """
    if not new_domain:
        return fig_data, fig_layout

    axes_remapping = {}
    new_axes = {}
    old_axes = []
    type_ = None

    for k, v in fig_layout.items():
        #todo: coloraxis; thickness, len, x, y
        if k.startswith("xaxis"):
            type_ = "xaxis"

        elif k.startswith("yaxis"):
            type_ = "yaxis"

        elif k.startswith("scene"):
            type_ = "scene"

        elif k.startswith("polar"):
            type_ = "polar"

        elif k.startswith("ternary"):
            type_ = "ternary"

        if type_:
            # axes start at 1, and the 1 is dropped
            num = "" if new_axes_start[type_] == 1 else new_axes_start[type_]
            new_axes_start[type_] += 1
            old_axes.append(k)

            new_axis, old_trace_axis, new_trace_axis = resize_axis(
                type_, k, v, num, new_domain)

            new_axes[new_axis] = v
            axes_remapping[old_trace_axis] = new_trace_axis

        type_ = None

    # need to remove old axes in case there is one with a very high number
    for axis in old_axes:
        fig_layout.pop(axis)

    fig_layout.update(new_axes)

    for trace in fig_data:
        reassign_axes(trace, axes_remapping)
        if "domain" in trace:
            resize_domain(trace, new_domain)

    for axis in fig_layout.values():
        reassign_attributes(axis, axes_remapping)

    return fig_data, fig_layout


def fig_data_and_layout(
        fig: Figure,
        i: int,
        domains: list[dict[str, list[float]]],
        which_layout: int,
        new_axes_start: dict[str, int]
) -> tuple[tuple | dict, dict]:
    """
    Get new data and layout for the specified figure

    :param fig: The current figure
    :param i: The index of the figure, used for which_layout
    :param which_layout: None to layer layouts, or an index of which arg to
    take the layout from
    :param domains: A list of dictionaries that contain keys of "x" and "y"
    and values that are lists of two floats form 0 to 1. The chart that
    corresponds with a domain will be resized to that domain. X and y can be
    excluded if only resizing on one axis.
    :param new_axes_start: A dict that keeps track of starting points when
    recreating axes
    :return: A tuple of figure data, figure layout
    """
    if domains:
        return resize(fig.to_dict()['data'], fig.to_dict()['layout'],
                      domains[i], new_axes_start)

    fig_layout = {}
    if not which_layout or which_layout == i:
        fig_layout.update(fig.to_dict()['layout'])

    return fig.data, fig_layout


def layer(
        *args: DeephavenFigure | Figure,
        which_layout: int = None,
        domains: list[dict[str, list[float]]] = None,
        # recreate_axes=True, TODO needed for faceting, marginals: control when axes are recreated
        unsafe_update: Callable = default_callback
) -> DeephavenFigure:
    """
    Layers the provided figures. Be default, the layouts are sequentially
    applied, so the layouts of later figures will override the layouts of early
    figures.

    :param args: The charts to layer
    :param which_layout: None to layer layouts, or an index of which arg to
    take the layout from. Currently only valid if domains are not specified.
    :param domains: A list of dictionaries that contain keys of "x" and "y"
    and values that are lists of two floats form 0 to 1. The chart that
    corresponds with a domain will be resized to that domain. Either x or y can
    be excluded if only resizing on one axis.
    :param unsafe_update: An update function that takes a figure as an
    argument and optionally returns a figure. If a figure is not returned,
    the plotly figure passed will be assumed to be the return value. Used to
    add any custom changes to the underlying plotly figure. Note that the
    existing data traces should not be removed. This may lead to unexpected
    behavior if traces are modified in a way that break data mappings.
    :return: The layered chart
    """
    if len(args) == 0:
        raise ValueError("No figures provided to compose")

    new_data = []
    new_layout = {}
    new_data_mappings = []
    new_has_template = False
    new_has_color = False

    # when recreating axes, need to keep track of start of new axes
    new_axes_start = {
        "xaxis": 1,
        "yaxis": 1,
        "scene": 1,
        "polar": 1,
        "ternary": 1
    }

    for i, arg in enumerate(args):
        if isinstance(arg, Figure):
            fig_data, fig_layout = fig_data_and_layout(
                arg, i, domains, which_layout, new_axes_start
            )

        elif isinstance(arg, DeephavenFigure):
            offset = len(new_data)
            if arg.has_subplots:
                raise NotImplementedError("Cannot currently add figure with subplots as a subplot")
            fig_data, fig_layout = fig_data_and_layout(
                arg.fig, i, domains, which_layout, new_axes_start
            )
            new_data_mappings += arg.copy_mappings(offset=offset)
            new_has_template = arg.has_template or new_has_template
            new_has_color = arg.has_color or new_has_color

        else:
            raise TypeError("All arguments must be of type Figure or DeephavenFigure")

        new_data += fig_data
        new_layout.update(fig_layout)

    new_fig = Figure(data=new_data, layout=new_layout)

    new_fig = unsafe_update(new_fig)

    # todo: this doesn't maintain call args, but that isn't currently needed
    return DeephavenFigure(
        fig=new_fig,
        data_mappings=new_data_mappings,
        has_template=new_has_template,
        has_color=new_has_color,
        has_subplots=True
    )


def validate_common_args(
        args: dict
) -> None:
    """
    Validate common args amongst plots

    :param args: The args to validate
    """
    if not isinstance(args["table"], Table):
        raise ValueError("Argument table is not of type Table")


def remap_scene_args(
        args: dict
) -> None:
    """
    Remap layout scenes args so that they are not converted to a list

    :param args: The args to remap
    """
    for arg in ["range_x", "range_y", "range_z", "log_x", "log_y", "log_z"]:
        args[arg + '_scene'] = args.pop(arg)


def trace_legend_generator(
        cols: list[str]
) -> Generator[dict]:
    """
    Adds the traces to the legend

    :param cols: The cols to label the trace with in the legend
    :returns: A generator that yields trace updates
    """
    for col in cols:
        yield {
            "name": col,
            "showlegend": True
        }


def preprocessed_fig(
        preprocesser: Callable,
        draw: Callable,
        keys: list[str],
        table: Table,
        args: dict[str, any],
        trace_generator: Generator[dict[str, any]],
        cols: str | list[str],
) -> DeephavenFigure:
    """
    Preprocess and return a figure

    :param preprocesser: A function that returns a tuple that contains
    (new table, first data columnn, second data column)
    :param draw: A draw function, generally from plotly express
    :param args: The args to pass to figure creation
    :param keys: A list of the variables to assign the preprocessed results to
    :param table: The table to use
    :param args: The args to passed to generate_figure
    :param trace_generator: The trace generator to use to pass to
    generate_figure
    :param cols: The columns that are being plotted
    :return: The resulting DeephavenFigure
    """
    output = preprocesser(table, cols)
    for k, v in zip(keys, output):
        args[k] = v

    return generate_figure(
        draw=draw,
        call_args=args,
        trace_generator=trace_generator,
        allow_callback=False
    )


def update_legend_and_titles(
        fig: DeephavenFigure,
        var: str,
        cols: list[str],
        is_list: bool,
        list_var_axis_name: str,
        list_val_axis_name: str,
        str_var_axis_name: str,
        str_val_axis_name: str
) -> None:
    """
    Update the legend and titles so they match plotly express (more or less)

    :param fig: The figure to update
    :param var: Which var to map to the first column. If "x", then the
    preprocessor output is mapped to table, x, y. If "y" then preprocessor
    output is mapped to table, y, x.
    :param cols: The columns that are used for the sake of updating the
    legend
    :param is_list: True if the cols were originally passed as a list
    :param str_var_axis_name: Name on the var axis if cols is a str
    :param str_val_axis_name: Name on the non-var axis if cols is a str
    :param list_var_axis_name: Name on the var axis if cols is a list
    :param list_val_axis_name: Name on the non-var axis if cols is a list
    """
    layout_update = {}
    other_var = "y" if var == "x" else "x"

    if is_list:
        update_traces(fig.fig, trace_legend_generator(cols))
        layout_update.update(
            legend_title_text="variable",
            legend_tracegroupgap=0
        )

        if list_var_axis_name:
            layout_update[f"{var}axis_title_text"] = list_var_axis_name

        if list_val_axis_name:
            layout_update[f"{other_var}axis_title_text"] = list_val_axis_name

    else:
        # ensure the legend is hidden (especially for hist)
        layout_update["showlegend"] = False

        if str_var_axis_name:
            layout_update[f"{var}axis_title_text"] = str_var_axis_name

        if str_val_axis_name:
            layout_update[f"{other_var}axis_title_text"] = str_val_axis_name

    fig.fig.update_layout(layout_update)


def preprocess_and_layer(
        preprocesser: Callable,
        draw: Callable,
        args: dict[str, any],
        var: str,
        orientation: str = None,
        str_var_axis_name: str = None,
        str_val_axis_name: str = None,
        list_var_axis_name: str = None,
        list_val_axis_name: str = None,
        skip_layer: bool = False,
) -> DeephavenFigure:
    """
    Given a preprocessing function, a draw function, and several
    columns, layer up the resulting figures

    :param preprocesser: A function that takes a table, list of cols
    and returns a tuple that contains
    (new table, first data columnn, second data column)
    :param draw: A draw function, generally from plotly express
    :param args: The args to pass to figure creation
    :param var: Which var to map to the first column. If "x", then the
    preprocessor output is mapped to table, x, y. If "y" then preprocessor
    output is mapped to table, y, x.
    :param orientation: optional orientation if it is needed
    :param str_var_axis_name: Name on the var axis if cols is a str
    :param str_val_axis_name: Name on the non-var axis if cols is a str
    :param list_var_axis_name: Name on the var axis if cols is a list
    :param list_val_axis_name: Name on the non-var axis if cols is a list
    :param skip_layer: If true, all columns are passed to the preprocess function
    and only one table is returned from it, so the layering step is skipped.
    Currently, it is assumed that hist is the only plot type using this.
    :return: The resulting DeephavenFigure
    """
    cols = args[var]
    # to mirror px, list_var_axis_name and legend should only be used when cols
    # are a list (regardless of length)
    is_list = isinstance(cols, list)
    cols = cols if is_list else [cols]
    keys = ["table", "x", "y"] if var == "x" else ["table", "y", "x"]
    table = args["table"]
    figs = []
    trace_generator = None

    if orientation:
        args["orientation"] = orientation

    create_fig = partial(
        preprocessed_fig,
        preprocesser, draw,
        keys, table, args
    )

    if skip_layer:
        figs.append(create_fig(trace_generator, cols))
        # currently, the only user of skip_layer is hist, so if another plot
        # type is passed here this will need to be refactored
        # hist should have the col name be the passed str if cols is a str
        str_var_axis_name = str_var_axis_name if is_list else cols[0]
    else:
        for col in cols:
            figs.append(create_fig(trace_generator, col))

            if not trace_generator:
                trace_generator = figs[0].trace_generator

    layered = layer(*figs, which_layout=0)

    # todo: pull this out?
    update_legend_and_titles(
        layered, var, cols, is_list,
        list_var_axis_name, list_val_axis_name,
        str_var_axis_name, str_val_axis_name
    )

    # call the callback now as it was not allowed during figure generation
    new_fig = args['unsafe_update'](layered)
    new_fig = new_fig if new_fig else layered

    return new_fig


def _make_subplots(
        rows=1,
        cols=1
):
    # todo: not yet implemented
    new_fig = subplots.make_subplots(rows=rows, cols=cols)
    return DeephavenFigure(new_fig)
